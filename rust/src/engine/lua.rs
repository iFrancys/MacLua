//! Parser for Steam plugin Lua files in `stplug-in/<appid>.lua`.
//!
//! Extracts:
//! - Depot decryption keys: `addappid(id, 1, "keyhex")` or `addappid(id, 0, "keyhex")`
//! - Manifest GIDs: `setManifestid(depot, gid)`
//! - Bare appids: `addappid(id)`

use std::collections::HashMap;
use regex::Regex;

#[derive(Debug, Clone, Default, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct ParsedLua {
    pub keys: HashMap<u32, String>,
    pub manifests: HashMap<u32, String>,
    pub bare: Vec<u32>,
}

pub fn parse_lua(content: &str) -> ParsedLua {
    let mut result = ParsedLua::default();

    // Regex for addappid with 3 arguments: addappid(depot, flag, "key")
    // e.g. addappid(1002, 1, "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef")
    let re_key = Regex::new(r#"addappid\s*\(\s*(\d+)\s*,\s*\d+\s*,\s*["']([0-9a-fA-F]{64})["']\s*\)"#).unwrap();
    for cap in re_key.captures_iter(content) {
        if let (Some(m_id), Some(m_key)) = (cap.get(1), cap.get(2)) {
            if let Ok(depot_id) = m_id.as_str().parse::<u32>() {
                result.keys.insert(depot_id, m_key.as_str().to_lowercase());
            }
        }
    }

    // Regex for addappid with 1 argument: addappid(appid)
    let re_bare = Regex::new(r#"addappid\s*\(\s*(\d+)\s*\)"#).unwrap();
    for cap in re_bare.captures_iter(content) {
        if let Some(m_id) = cap.get(1) {
            if let Ok(appid) = m_id.as_str().parse::<u32>() {
                result.bare.push(appid);
            }
        }
    }

    // Regex for setManifestid(depot, "gid") or setManifestid(depot, gid)
    let re_man = Regex::new(r#"setManifestid\s*\(\s*(\d+)\s*,\s*["']?(\d+)["']?\s*\)"#).unwrap();
    for cap in re_man.captures_iter(content) {
        if let (Some(m_dep), Some(m_gid)) = (cap.get(1), cap.get(2)) {
            if let Ok(depot_id) = m_dep.as_str().parse::<u32>() {
                result.manifests.insert(depot_id, m_gid.as_str().to_string());
            }
        }
    }

    result
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_lua() {
        let script = r#"
            -- Test Lua Plugin
            addappid(400)
            addappid(401, 1, "0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF")
            setManifestid(401, "1234567890123456789")
        "#;
        let parsed = parse_lua(script);
        assert_eq!(parsed.bare, vec![400]);
        assert_eq!(
            parsed.keys.get(&401).unwrap(),
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        );
        assert_eq!(parsed.manifests.get(&401).unwrap(), "1234567890123456789");
    }
}
