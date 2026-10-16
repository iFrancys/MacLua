//! Multi-database manifest sources provider (Sushi, Ryuu, Hubcap/Morrenus).
//!
//! Allows downloading .lua and .manifest files anonymously without requiring an API key (Sushi & Ryuu),
//! while supporting optional Morrenus/Hubcap API keys for premium databases.

use std::collections::HashMap;
use std::io::{Cursor, Read};
use regex::Regex;
use serde::{Deserialize, Serialize};

use crate::engine::{depotkeys, license};
use crate::util::paths;

pub const SUSHI_PRIMARY: &str = "https://raw.githubusercontent.com/sushi-dev55/sushitools-games-repo/main";
pub const SUSHI_ALT: &str = "https://raw.githubusercontent.com/sushi-dev55-alt/sushitools-games-repo-alt/refs/heads/main";
pub const RYUU_CHECK: &str = "http://167.235.229.108/check_apis";
pub const RYUU_DOWNLOAD: &str = "http://167.235.229.108";
pub const HUBCAP_BASE: &str = "https://hubcapmanifest.com/api/v1/manifest";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SourceStatus {
    pub name: String,
    pub display_name: String,
    pub available: bool,
    pub needs_key: bool,
    pub description: String,
}

#[derive(Debug, Clone)]
pub struct ExtractedGame {
    pub appid: u32,
    pub lua: String,
    pub manifests: HashMap<String, Vec<u8>>,
    pub source: String,
}

#[derive(Debug, thiserror::Error)]
pub enum SourceError {
    #[error("richiesta di rete fallita: {0}")]
    Network(#[from] reqwest::Error),
    #[error("archivio zip non valido o corrotto: {0}")]
    Zip(#[from] zip::result::ZipError),
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),
    #[error("nessun database disponibile per questo appid: {0}")]
    NotFound(u32),
    #[error("errore durante l'estrazione: {0}")]
    Extraction(String),
}

/// Checks availability of game manifests across multiple databases.
pub async fn check_sources(
    client: &reqwest::Client,
    appid: u32,
    hubcap_key: Option<&str>,
) -> Vec<SourceStatus> {
    let mut results = Vec::new();

    // 1. Sushi (Free GitHub repositories)
    let sushi_url = format!("{}/{}.zip", SUSHI_PRIMARY, appid);
    let sushi_available = match client.head(&sushi_url).send().await {
        Ok(res) => res.status().is_success(),
        Err(_) => {
            let alt_url = format!("{}/{}.zip", SUSHI_ALT, appid);
            client.head(&alt_url).send().await.map(|r| r.status().is_success()).unwrap_or(false)
        }
    };
    results.push(SourceStatus {
        name: "sushi".to_string(),
        display_name: "Sushi".to_string(),
        available: sushi_available,
        needs_key: false,
        description: "Database gratuito della community GitHub (nessuna chiave richiesta)".to_string(),
    });

    // 2. Ryuu (Manifest backend)
    let ryuu_url = format!("{}?appid={}", RYUU_CHECK, appid);
    let ryuu_available = match client
        .get(&ryuu_url)
        .header("User-Agent", "secretgoonpoon")
        .timeout(std::time::Duration::from_secs(4))
        .send()
        .await
    {
        Ok(res) => {
            if let Ok(text) = res.text().await {
                text.contains("\"available\"")
            } else {
                false
            }
        }
        Err(_) => false,
    };
    results.push(SourceStatus {
        name: "ryuu".to_string(),
        display_name: "Ryuu".to_string(),
        available: ryuu_available,
        needs_key: false,
        description: "Database pubblico di manifest (nessuna chiave richiesta)".to_string(),
    });

    // 3. Hubcap / Sadie (Requires Morrenus API Key)
    let has_key = hubcap_key.map(|k| !k.trim().is_empty()).unwrap_or(false);
    let hubcap_available = if has_key {
        let key = hubcap_key.unwrap().trim();
        let hc_url = format!("{}/{}?api_key={}", HUBCAP_BASE, appid, key);
        client.head(&hc_url).send().await.map(|r| r.status().is_success()).unwrap_or(false)
    } else {
        false
    };
    results.push(SourceStatus {
        name: "hubcap".to_string(),
        display_name: "Sadie / Hubcap".to_string(),
        available: hubcap_available,
        needs_key: true,
        description: "Database Hubcapmanifest (richiede chiave API smm_...)".to_string(),
    });

    results
}

/// Downloads and extracts the game's lua and manifest files from the specified or best source.
pub async fn fetch_game(
    client: &reqwest::Client,
    appid: u32,
    preferred_source: Option<&str>,
    hubcap_key: Option<&str>,
) -> Result<ExtractedGame, SourceError> {
    let source = preferred_source.unwrap_or("auto").to_lowercase();

    // Strategy 1: Hubcap if explicitly selected or auto with key present
    if source == "hubcap" || (source == "auto" && hubcap_key.map(|k| !k.trim().is_empty()).unwrap_or(false)) {
        if let Some(key) = hubcap_key {
            let key = key.trim();
            if !key.is_empty() {
                let hc_url = format!("{}/{}?api_key={}", HUBCAP_BASE, appid, key);
                if let Ok(res) = client.get(&hc_url).send().await {
                    if res.status().is_success() {
                        if let Ok(bytes) = res.bytes().await {
                            if let Ok(extracted) = extract_zip_payload(appid, &bytes, "hubcap") {
                                return Ok(extracted);
                            }
                        }
                    }
                }
            }
        }
        if source == "hubcap" {
            return Err(SourceError::NotFound(appid));
        }
    }

    // Strategy 2: Sushi (Primary or Alt)
    if source == "sushi" || source == "auto" {
        for base in [SUSHI_PRIMARY, SUSHI_ALT] {
            let url = format!("{}/{}.zip", base, appid);
            if let Ok(res) = client.get(&url).send().await {
                if res.status().is_success() {
                    let bytes = res.bytes().await?;
                    if let Ok(extracted) = extract_zip_payload(appid, &bytes, "sushi") {
                        return Ok(extracted);
                    }
                }
            }
        }
        if source == "sushi" {
            return Err(SourceError::NotFound(appid));
        }
    }

    // Strategy 3: Ryuu
    if source == "ryuu" || source == "auto" {
        let url = format!("{}/{}", RYUU_DOWNLOAD, appid);
        if let Ok(res) = client.get(&url).header("User-Agent", "secretgoonpoon").send().await {
            if res.status().is_success() {
                let bytes = res.bytes().await?;
                if let Ok(extracted) = extract_zip_payload(appid, &bytes, "ryuu") {
                    return Ok(extracted);
                }
            }
        }
    }

    Err(SourceError::NotFound(appid))
}

/// Safely extracts the `<appid>.lua` and `.manifest` files from a ZIP archive.
/// Normalizes path separators (handling both Windows `\` and Unix `/`).
fn extract_zip_payload(appid: u32, zip_bytes: &[u8], source_name: &str) -> Result<ExtractedGame, SourceError> {
    let reader = Cursor::new(zip_bytes);
    let mut archive = zip::ZipArchive::new(reader)?;

    let mut lua_text: Option<String> = None;
    let mut manifests = HashMap::new();
    let want_lua_name = format!("{}.lua", appid);

    for i in 0..archive.len() {
        let mut file = archive.by_index(i)?;
        let raw_name = file.name().to_string();
        let normalized = raw_name.replace('\\', "/");
        let base_name = normalized.rsplit('/').next().unwrap_or(&normalized);

        if base_name.eq_ignore_ascii_case(&want_lua_name) {
            let mut text = String::new();
            file.read_to_string(&mut text)?;
            lua_text = Some(text);
        } else if base_name.ends_with(".manifest") {
            let mut data = Vec::new();
            file.read_to_end(&mut data)?;
            manifests.insert(base_name.to_string(), data);
        }
    }

    let lua = lua_text.ok_or_else(|| {
        SourceError::Extraction(format!("nello zip manca {}.lua", appid))
    })?;

    Ok(ExtractedGame {
        appid,
        lua,
        manifests,
        source: source_name.to_string(),
    })
}

/// Comments out setManifestid lines so the app isn't pinned to an old version,
/// allowing Steam to automatically manage downloads and updates (same logic as LuaTools).
pub fn comment_out_manifest_pins(lua: &str) -> String {
    let re = Regex::new(r"(?i)^(\s*)(setManifestid\s*\()").unwrap();
    let mut output = Vec::new();

    for line in lua.lines() {
        let trimmed = line.trim_start();
        if trimmed.starts_with("--") {
            output.push(line.to_string());
        } else if re.is_match(line) {
            output.push(re.replace(line, "$1-- $2").to_string());
        } else {
            output.push(line.to_string());
        }
    }

    output.join("\n")
}

/// Installs the extracted game payload into Steam:
/// - stplug-in/{appid}.lua (with manifest pins commented out if auto_update is true)
/// - depotcache/{name}.manifest
/// - Syncs depot keys to config.vdf
/// - Poisons packageinfo.vdf with appid and depotids
/// - Cleans up any fake appmanifests (ensuring clean native Steam interface)
pub fn install_game(
    extracted: &ExtractedGame,
    auto_update: bool,
) -> Result<(), SourceError> {
    let stplug_dir = paths::stplug_in_dir();
    let _ = std::fs::create_dir_all(&stplug_dir);

    // 1. Prepare and write Lua
    let final_lua = if auto_update {
        comment_out_manifest_pins(&extracted.lua)
    } else {
        extracted.lua.clone()
    };

    let lua_path = stplug_dir.join(format!("{}.lua", extracted.appid));
    std::fs::write(&lua_path, &final_lua)?;

    // 2. Write manifests to depotcache
    let depotcache = paths::depotcache_dir();
    let _ = std::fs::create_dir_all(&depotcache);
    for (name, bytes) in &extracted.manifests {
        let dest = depotcache.join(name);
        let _ = std::fs::write(dest, bytes);
    }

    // 3. Collect keys and sync config.vdf
    let keys = depotkeys::collect_keys(&stplug_dir);
    let config_vdf = paths::config_vdf_path();
    let _ = depotkeys::sync_config_vdf(&config_vdf, &keys);

    // 4. Poison packageinfo.vdf
    let mut appids = std::collections::HashSet::new();
    let mut depotids = std::collections::HashSet::new();
    for (did, (aid, _)) in &keys {
        appids.insert(*aid);
        depotids.insert(*did);
    }
    appids.insert(extracted.appid);

    let pkginfo = paths::packageinfo_path();
    if pkginfo.exists() {
        let _ = license::poison_packageinfo(&pkginfo, &appids, &depotids);
    }

    // 5. Clean up any fake appmanifests to ensure classic normal interface in Steam
    let steamapps = paths::steamapps_dir();
    let _ = crate::engine::install::cleanup_broken_appmanifests(&steamapps);

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_comment_out_manifest_pins() {
        let input = "addappid(1332010)\nsetManifestid(1332011, \"12345\", 0)\naddappid(1332012)";
        let output = comment_out_manifest_pins(input);
        assert!(output.contains("-- setManifestid(1332011, \"12345\", 0)"));
        assert!(output.contains("addappid(1332010)"));
    }

    #[test]
    fn test_already_commented_manifest_pins() {
        let input = "addappid(1332010)\n-- setManifestid(1332011, \"12345\", 0)";
        let output = comment_out_manifest_pins(input);
        assert_eq!(output, input);
    }
}
