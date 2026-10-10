//! Depot keys cache and config.vdf synchronization using AST KeyValues.

use std::collections::HashMap;
use std::fs::File;
use std::io::Write;
use std::path::{Path, PathBuf};
use base64::Engine;
use base64::prelude::BASE64_STANDARD;

use super::keyvalues::KeyValues;
use super::lua::parse_lua;

#[derive(Debug, thiserror::Error)]
pub enum DepotKeyError {
    #[error("invalid hex string for depot {0}")]
    InvalidHex(u32),
    #[error("key length must be 32 bytes for depot {0}, got {1}")]
    InvalidLength(u32, usize),
    #[error("no key in cache for depot {0}")]
    NotFound(u32),
    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),
    #[error("KeyValues parsing error: {0}")]
    Kv(#[from] super::keyvalues::KvError),
}

/// Collects all `{depot_id: (appid, key_hex)}` from `<appid>.lua` files in `stplug_dir`.
pub fn collect_keys<P: AsRef<Path>>(stplug_dir: P) -> HashMap<u32, (u32, String)> {
    let mut map = HashMap::new();
    let entries = match std::fs::read_dir(stplug_dir.as_ref()) {
        Ok(e) => e,
        Err(_) => return map,
    };

    for entry in entries.flatten() {
        let path = entry.path();
        if path.extension().and_then(|e| e.to_str()) == Some("lua") {
            if let Some(stem) = path.file_stem().and_then(|s| s.to_str()) {
                if let Ok(appid) = stem.parse::<u32>() {
                    if let Ok(content) = std::fs::read_to_string(&path) {
                        let parsed = parse_lua(&content);
                        for (depot_id, key_hex) in parsed.keys {
                            map.insert(depot_id, (appid, key_hex));
                        }
                    }
                }
            }
        }
    }

    map
}

/// Path to cached yaml key: `<cache_dir>/depotkey_<depot_id>.yaml`.
pub fn key_path<P: AsRef<Path>>(cache_dir: P, depot_id: u32) -> PathBuf {
    cache_dir.as_ref().join(format!("depotkey_{}.yaml", depot_id))
}

/// Writes `depotkey_<d>.yaml` atomically with permissions 0600.
pub fn write_cache<P: AsRef<Path>>(
    cache_dir: P,
    appid: u32,
    depot_id: u32,
    key_hex: &str,
) -> Result<PathBuf, DepotKeyError> {
    let raw = hex::decode(key_hex).map_err(|_| DepotKeyError::InvalidHex(depot_id))?;
    if raw.len() != 32 {
        return Err(DepotKeyError::InvalidLength(depot_id, raw.len()));
    }

    std::fs::create_dir_all(cache_dir.as_ref())?;
    let b64_key = BASE64_STANDARD.encode(&raw);
    let body = format!(
        "appId: {}\ndepotId: {}\nkey: {}\nmanaged: true\n",
        appid, depot_id, b64_key
    );

    let target = key_path(cache_dir.as_ref(), depot_id);
    if target.exists() {
        if let Ok(existing) = std::fs::read_to_string(&target) {
            if existing == body {
                return Ok(target);
            }
        }
    }

    let tmp = format!("{}.tmp", target.display());
    {
        let mut f = File::create(&tmp)?;
        f.write_all(body.as_bytes())?;
        f.flush()?;
    }
    std::fs::rename(&tmp, &target)?;

    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = std::fs::set_permissions(&target, std::fs::Permissions::from_mode(0o600));
    }

    Ok(target)
}

/// Loads raw 32-byte decryption key from yaml cache.
pub fn load_key<P: AsRef<Path>>(cache_dir: P, depot_id: u32) -> Result<[u8; 32], DepotKeyError> {
    let p = key_path(cache_dir, depot_id);
    let text = std::fs::read_to_string(&p).map_err(|_| DepotKeyError::NotFound(depot_id))?;

    for line in text.lines() {
        if let Some(rest) = line.strip_prefix("key:") {
            let trimmed = rest.trim();
            if let Ok(bytes) = BASE64_STANDARD.decode(trimmed) {
                if bytes.len() == 32 {
                    let mut key = [0u8; 32];
                    key.copy_from_slice(&bytes);
                    return Ok(key);
                }
            }
        }
    }

    Err(DepotKeyError::NotFound(depot_id))
}

/// Synchronizes decryption keys into `config.vdf` using AST KeyValues1.
pub fn sync_config_vdf<P: AsRef<Path>>(
    config_vdf_path: P,
    keys_map: &HashMap<u32, (u32, String)>,
) -> Result<usize, DepotKeyError> {
    if !config_vdf_path.as_ref().is_file() {
        return Ok(0);
    }

    let content = std::fs::read_to_string(config_vdf_path.as_ref())?;
    let mut kv = KeyValues::parse(&content)?;

    // Locate or create path: InstallConfigStore / Software / Valve / Steam / depots
    let mut updated_count = 0;
    if let Some((_, root_val)) = kv.root.iter_mut().find(|(k, _)| k.eq_ignore_ascii_case("InstallConfigStore")) {
        let sw = root_val.get_or_create_section("Software");
        let valve = sw.get_or_create_section("Valve");
        let steam = valve.get_or_create_section("Steam");
        let depots_sec = steam.get_or_create_section("depots");

        for (depot_id, (_, key_hex)) in keys_map {
            let depot_str = depot_id.to_string();
            let dep_entry = depots_sec.get_or_create_section(&depot_str);
            dep_entry.set_str("DecryptionKey", key_hex);
            updated_count += 1;
        }
    }

    let serialized = kv.serialize();
    let tmp = format!("{}.tmp.maclua", config_vdf_path.as_ref().display());
    {
        let mut f = File::create(&tmp)?;
        f.write_all(serialized.as_bytes())?;
        f.flush()?;
    }
    std::fs::rename(&tmp, config_vdf_path.as_ref())?;

    Ok(updated_count)
}
