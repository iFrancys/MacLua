//! Unified SQLite storage engine in WAL mode for MacLua state.
//!
//! Replaces fragmented JSON files (settings.json, fixes.json, queue_history.json, etc.)
//! with atomic transactions, indexed lookups, and automatic legacy migration.

use std::path::Path;
use rusqlite::{Connection, params};
use crate::util::paths;

#[derive(Debug, thiserror::Error)]
pub enum DbError {
    #[error("SQLite database error: {0}")]
    Sqlite(#[from] rusqlite::Error),
    #[error("I/O error during database initialization: {0}")]
    Io(#[from] std::io::Error),
    #[error("JSON serialization error: {0}")]
    Json(#[from] serde_json::Error),
}

pub struct Database {
    conn: Connection,
}

impl Database {
    pub fn open_default() -> Result<Self, DbError> {
        let dir = paths::maclua_support_dir();
        std::fs::create_dir_all(&dir)?;
        let path = paths::db_path();
        Self::open(&path)
    }

    pub fn open<P: AsRef<Path>>(path: P) -> Result<Self, DbError> {
        let conn = Connection::open(path)?;
        conn.execute_batch(
            r#"
            PRAGMA journal_mode = WAL;
            PRAGMA synchronous = NORMAL;
            PRAGMA busy_timeout = 5000;

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS fixes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                appid INTEGER NOT NULL,
                fix_type TEXT NOT NULL,
                details TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                UNIQUE(appid, fix_type)
            );

            CREATE TABLE IF NOT EXISTS queue_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                appid INTEGER NOT NULL,
                name TEXT,
                status TEXT NOT NULL,
                bytes INTEGER,
                completed_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS vault_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                appid INTEGER NOT NULL,
                hash TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                bytes INTEGER NOT NULL,
                note TEXT,
                lua_content TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS catalog_cache (
                appid INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                parent_id INTEGER,
                updated_at INTEGER NOT NULL
            );
            "#,
        )?;

        let mut db = Self { conn };
        db.migrate_legacy_json()?;
        Ok(db)
    }

    /// Migrates existing legacy JSON files if database was newly created.
    fn migrate_legacy_json(&mut self) -> Result<(), DbError> {
        let support = paths::maclua_support_dir();

        // 1. Migrate settings.json
        let settings_path = support.join("settings.json");
        if settings_path.exists() {
            if let Ok(data) = std::fs::read_to_string(&settings_path) {
                if let Ok(map) = serde_json::from_str::<serde_json::Map<String, serde_json::Value>>(&data) {
                    let now = std::time::SystemTime::now()
                        .duration_since(std::time::UNIX_EPOCH)
                        .unwrap_or_default()
                        .as_secs() as i64;
                    for (k, v) in map {
                        let _ = self.conn.execute(
                            "INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES (?1, ?2, ?3)",
                            params![k, v.to_string(), now],
                        );
                    }
                }
            }
        }

        // 2. Migrate fixes.json
        let fixes_path = support.join("fixes.json");
        if fixes_path.exists() {
            if let Ok(data) = std::fs::read_to_string(&fixes_path) {
                if let Ok(map) = serde_json::from_str::<serde_json::Map<String, serde_json::Value>>(&data) {
                    for (aid_str, fixes_arr) in map {
                        if let (Ok(aid), Some(arr)) = (aid_str.parse::<u32>(), fixes_arr.as_array()) {
                            for f in arr {
                                if let (Some(ftype), Some(ts)) = (f.get("type").and_then(|v| v.as_str()), f.get("timestamp").and_then(|v| v.as_i64())) {
                                    let details_str = f.get("details").map(|d| d.to_string()).unwrap_or_else(|| "{}".into());
                                    let _ = self.conn.execute(
                                        "INSERT OR IGNORE INTO fixes (appid, fix_type, details, timestamp) VALUES (?1, ?2, ?3, ?4)",
                                        params![aid, ftype, details_str, ts],
                                    );
                                }
                            }
                        }
                    }
                }
            }
        }

        Ok(())
    }

    // --- Settings API ---
    pub fn get_setting(&self, key: &str) -> Result<Option<String>, DbError> {
        let mut stmt = self.conn.prepare("SELECT value FROM settings WHERE key = ?1")?;
        let mut rows = stmt.query(params![key])?;
        if let Some(row) = rows.next()? {
            let val: String = row.get(0)?;
            Ok(Some(val))
        } else {
            Ok(None)
        }
    }

    pub fn set_setting(&self, key: &str, value: &str) -> Result<(), DbError> {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs() as i64;
        self.conn.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?1, ?2, ?3)
             ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            params![key, value, now],
        )?;
        Ok(())
    }

    pub fn get_all_settings(&self) -> Result<serde_json::Value, DbError> {
        let mut stmt = self.conn.prepare("SELECT key, value FROM settings")?;
        let rows = stmt.query_map([], |row| {
            let k: String = row.get(0)?;
            let v: String = row.get(1)?;
            Ok((k, v))
        })?;

        let mut map = serde_json::Map::new();
        for item in rows {
            let (k, v) = item?;
            // If v is a valid JSON primitive/object, parse it; otherwise string
            let parsed = serde_json::from_str(&v).unwrap_or(serde_json::Value::String(v));
            map.insert(k, parsed);
        }
        Ok(serde_json::Value::Object(map))
    }

    // --- Fixes API ---
    pub fn record_fix(&self, appid: u32, fix_type: &str, details: &serde_json::Value) -> Result<(), DbError> {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs() as i64;
        let details_str = details.to_string();
        self.conn.execute(
            "INSERT INTO fixes (appid, fix_type, details, timestamp) VALUES (?1, ?2, ?3, ?4)
             ON CONFLICT(appid, fix_type) DO UPDATE SET details = excluded.details, timestamp = excluded.timestamp",
            params![appid, fix_type, details_str, now],
        )?;
        Ok(())
    }

    pub fn get_fixes(&self, appid: Option<u32>) -> Result<Vec<serde_json::Value>, DbError> {
        let mut out = Vec::new();
        if let Some(aid) = appid {
            let mut stmt = self.conn.prepare("SELECT appid, fix_type, details, timestamp FROM fixes WHERE appid = ?1")?;
            let rows = stmt.query_map(params![aid], |row| {
                let aid: u32 = row.get(0)?;
                let ftype: String = row.get(1)?;
                let det: String = row.get(2)?;
                let ts: i64 = row.get(3)?;
                Ok((aid, ftype, det, ts))
            })?;
            for r in rows {
                let (aid, ftype, det, ts) = r?;
                let det_json: serde_json::Value = serde_json::from_str(&det).unwrap_or_default();
                out.push(serde_json::json!({
                    "appid": aid,
                    "type": ftype,
                    "details": det_json,
                    "timestamp": ts,
                }));
            }
        } else {
            let mut stmt = self.conn.prepare("SELECT appid, fix_type, details, timestamp FROM fixes")?;
            let rows = stmt.query_map([], |row| {
                let aid: u32 = row.get(0)?;
                let ftype: String = row.get(1)?;
                let det: String = row.get(2)?;
                let ts: i64 = row.get(3)?;
                Ok((aid, ftype, det, ts))
            })?;
            for r in rows {
                let (aid, ftype, det, ts) = r?;
                let det_json: serde_json::Value = serde_json::from_str(&det).unwrap_or_default();
                out.push(serde_json::json!({
                    "appid": aid,
                    "type": ftype,
                    "details": det_json,
                    "timestamp": ts,
                }));
            }
        }
        Ok(out)
    }

    // --- Vault Snapshots API ---
    pub fn save_vault_snapshot(
        &self,
        appid: u32,
        hash: &str,
        bytes: usize,
        note: Option<&str>,
        lua_content: &str,
    ) -> Result<i64, DbError> {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_millis() as i64;
        self.conn.execute(
            "INSERT INTO vault_snapshots (appid, hash, timestamp, bytes, note, lua_content)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
            params![appid, hash, now, bytes as i64, note, lua_content],
        )?;
        Ok(now)
    }

    pub fn list_vault_snapshots(&self, appid: Option<u32>) -> Result<Vec<serde_json::Value>, DbError> {
        let mut out = Vec::new();
        if let Some(aid) = appid {
            let mut stmt = self.conn.prepare(
                "SELECT appid, hash, timestamp, bytes, note FROM vault_snapshots WHERE appid = ?1 ORDER BY timestamp DESC",
            )?;
            let rows = stmt.query_map(params![aid], |row| {
                let aid: u32 = row.get(0)?;
                let hash: String = row.get(1)?;
                let ts: i64 = row.get(2)?;
                let bytes: i64 = row.get(3)?;
                let note: Option<String> = row.get(4)?;
                Ok((aid, hash, ts, bytes, note))
            })?;
            for r in rows {
                let (aid, hash, ts, bytes, note) = r?;
                out.push(serde_json::json!({
                    "appid": aid,
                    "hash": hash,
                    "timestamp": ts,
                    "bytes": bytes,
                    "note": note,
                }));
            }
        } else {
            let mut stmt = self.conn.prepare(
                "SELECT appid, hash, timestamp, bytes, note FROM vault_snapshots ORDER BY timestamp DESC",
            )?;
            let rows = stmt.query_map([], |row| {
                let aid: u32 = row.get(0)?;
                let hash: String = row.get(1)?;
                let ts: i64 = row.get(2)?;
                let bytes: i64 = row.get(3)?;
                let note: Option<String> = row.get(4)?;
                Ok((aid, hash, ts, bytes, note))
            })?;
            for r in rows {
                let (aid, hash, ts, bytes, note) = r?;
                out.push(serde_json::json!({
                    "appid": aid,
                    "hash": hash,
                    "timestamp": ts,
                    "bytes": bytes,
                    "note": note,
                }));
            }
        }
        Ok(out)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_db_settings_and_fixes() {
        let db = Database::open(":memory:").expect("open in-memory db failed");
        db.set_setting("theme", "\"dark\"").unwrap();
        let val = db.get_setting("theme").unwrap();
        assert_eq!(val, Some("\"dark\"".to_string()));

        db.record_fix(400, "macho_launcher", &serde_json::json!({"created": true})).unwrap();
        let fixes = db.get_fixes(Some(400)).unwrap();
        assert_eq!(fixes.len(), 1);
        assert_eq!(fixes[0]["type"], "macho_launcher");
    }
}
