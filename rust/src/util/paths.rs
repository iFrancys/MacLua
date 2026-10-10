//! Standard Steam and MacLua paths on macOS.

use std::path::PathBuf;

pub fn home_dir() -> PathBuf {
    std::env::var("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("/Users/Shared"))
}

pub fn maclua_support_dir() -> PathBuf {
    home_dir().join("Library/Application Support/MacLua")
}

pub fn db_path() -> PathBuf {
    maclua_support_dir().join("maclua.db")
}

pub fn token_path() -> PathBuf {
    maclua_support_dir().join("bridge_token")
}

pub fn vault_dir() -> PathBuf {
    maclua_support_dir().join("vault")
}

pub fn steam_root() -> PathBuf {
    home_dir().join("Library/Application Support/Steam")
}

pub fn steamapps_dir() -> PathBuf {
    steam_root().join("steamapps")
}

pub fn appcache_dir() -> PathBuf {
    steam_root().join("appcache")
}

pub fn depotcache_dir() -> PathBuf {
    steam_root().join("depotcache")
}

pub fn stplug_in_dir() -> PathBuf {
    // Primary path: steamapps/common/stplug-in
    let primary = steamapps_dir().join("common/stplug-in");
    if primary.exists() {
        return primary;
    }
    // Fallback: steam_root/stplug-in
    let fallback = steam_root().join("stplug-in");
    if fallback.exists() {
        return fallback;
    }
    primary
}

pub fn config_vdf_path() -> PathBuf {
    steam_root().join("config/config.vdf")
}

pub fn packageinfo_path() -> PathBuf {
    appcache_dir().join("packageinfo.vdf")
}

pub fn appinfo_path() -> PathBuf {
    appcache_dir().join("appinfo.vdf")
}

pub fn loginusers_path() -> PathBuf {
    steam_root().join("config/loginusers.vdf")
}
