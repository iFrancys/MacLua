//! Structured appinfo.vdf binary parser.
//!
//! Replaces byte scanning with structured offset navigation, indexed string table resolution,
//! and strongly-typed App record inspection.

use std::io::Cursor;
use std::path::Path;
use byteorder::{LittleEndian, ReadBytesExt};

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct AppDepotInfo {
    pub id: u32,
    pub oslist: Option<String>,
    pub gid: Option<String>,
    pub size: Option<u64>,
    pub shared: Option<u32>,
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct AppConfigInfo {
    pub name: Option<String>,
    pub installdir: Option<String>,
    pub parent_appid: Option<u32>,
    pub build_id: Option<u32>,
}

#[derive(Debug, thiserror::Error)]
pub enum AppInfoError {
    #[error("file too short for appinfo header")]
    FileTooShort,
    #[error("app {0} not found in appinfo.vdf cache")]
    AppNotFound(u32),
    #[error("string table index out of bounds")]
    StringTableOutOfBounds,
    #[error("binary parsing error at offset 0x{0:x}")]
    ParseError(usize),
    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),
}

pub struct AppInfoReader {
    data: Vec<u8>,
    string_table: Vec<String>,
}

impl AppInfoReader {
    pub fn open<P: AsRef<Path>>(path: P) -> Result<Self, AppInfoError> {
        let data = std::fs::read(path)?;
        Self::from_bytes(data)
    }

    pub fn from_bytes(data: Vec<u8>) -> Result<Self, AppInfoError> {
        if data.len() < 16 {
            return Err(AppInfoError::FileTooShort);
        }

        // Read string table offset from header (usually at offset 8)
        let mut cur = Cursor::new(&data[8..12]);
        let str_table_offset = cur.read_u32::<LittleEndian>()? as usize;

        let mut string_table = Vec::new();
        if str_table_offset > 0 && str_table_offset + 4 <= data.len() {
            let mut str_cur = Cursor::new(&data[str_table_offset..str_table_offset + 4]);
            let count = str_cur.read_u32::<LittleEndian>()? as usize;
            let mut off = str_table_offset + 4;
            for _ in 0..count {
                if off >= data.len() {
                    break;
                }
                if let Some(pos) = data[off..].iter().position(|&b| b == 0) {
                    let s = String::from_utf8_lossy(&data[off..off + pos]).to_string();
                    string_table.push(s);
                    off += pos + 1;
                } else {
                    break;
                }
            }
        }

        Ok(Self { data, string_table })
    }

    /// Finds the binary span of an AppID.
    fn find_app_span(&self, appid: u32) -> Option<(usize, usize)> {
        // App records start with binary pattern: node i32 with key index 1 == "appid"
        // Pattern: 0x02, 0x01, 0x00, 0x00, 0x00 followed by appid (u32 LE)
        let pattern = [0x02, 0x01, 0x00, 0x00, 0x00];
        let appid_bytes = appid.to_le_bytes();

        let mut i = 0;
        let n = self.data.len();
        while i + 9 <= n {
            if self.data[i..i + 5] == pattern && self.data[i + 5..i + 9] == appid_bytes {
                let start = if i >= 5 { i - 5 } else { i };
                // Find next record or end
                let mut next_start = n;
                let mut j = i + 9;
                while j + 5 <= n {
                    if self.data[j..j + 5] == pattern {
                        next_start = if j >= 5 { j - 5 } else { j };
                        break;
                    }
                    j += 1;
                }
                return Some((start, next_start));
            }
            i += 1;
        }

        None
    }

    /// Parses the raw KeyValues tree for an AppID.
    pub fn get_app_tree(&self, appid: u32) -> Result<Vec<(String, AppValue)>, AppInfoError> {
        let (start, end) = self.find_app_span(appid).ok_or(AppInfoError::AppNotFound(appid))?;
        let mut off = start;
        let (tree, _) = parse_indexed_bkv(&self.data, &self.string_table, &mut off, end)?;
        // Find "appinfo" node
        for (k, v) in tree {
            if k == "appinfo" {
                if let AppValue::Section(children) = v {
                    return Ok(children);
                }
            }
        }
        Ok(Vec::new())
    }

    /// Extracts depot list for an AppID.
    pub fn get_depots(&self, appid: u32) -> Result<Vec<AppDepotInfo>, AppInfoError> {
        let tree = self.get_app_tree(appid)?;
        let mut out = Vec::new();

        if let Some(depots_sec) = find_child(&tree, "depots") {
            if let AppValue::Section(depot_items) = depots_sec {
                for (k, v) in depot_items {
                    if let Ok(depot_id) = k.parse::<u32>() {
                        if let AppValue::Section(fields) = v {
                            let mut oslist = None;
                            let mut gid = None;
                            let mut size = None;
                            let mut shared = None;

                            if let Some(AppValue::String(s)) = find_child(fields, "oslist") {
                                oslist = Some(s.clone());
                            }
                            if let Some(AppValue::Section(manifests)) = find_child(fields, "manifests") {
                                if let Some(AppValue::String(g)) = find_child(manifests, "public") {
                                    gid = Some(g.clone());
                                } else if let Some(AppValue::Section(pub_sec)) = find_child(manifests, "public") {
                                    if let Some(AppValue::String(g)) = find_child(pub_sec, "gid") {
                                        gid = Some(g.clone());
                                    }
                                }
                            }
                            if let Some(AppValue::String(s)) = find_child(fields, "maxsize") {
                                size = s.parse::<u64>().ok();
                            }
                            if let Some(AppValue::String(s)) = find_child(fields, "sharedinstall") {
                                shared = s.parse::<u32>().ok();
                            }

                            out.push(AppDepotInfo {
                                id: depot_id,
                                oslist,
                                gid,
                                size,
                                shared,
                            });
                        }
                    }
                }
            }
        }

        Ok(out)
    }

    /// Extracts parent AppID if this is a DLC or expansion.
    pub fn get_parent(&self, appid: u32) -> Option<u32> {
        let tree = self.get_app_tree(appid).ok()?;
        if let Some(common) = find_child(&tree, "common") {
            if let AppValue::Section(fields) = common {
                if let Some(AppValue::String(s)) = find_child(fields, "parent") {
                    return s.parse::<u32>().ok();
                }
            }
        }
        None
    }

    /// Returns list of DLC AppIDs associated with this app.
    pub fn get_dlcs(&self, appid: u32) -> Vec<u32> {
        let mut dlcs = Vec::new();
        if let Ok(tree) = self.get_app_tree(appid) {
            if let Some(extended) = find_child(&tree, "extended") {
                if let AppValue::Section(fields) = extended {
                    if let Some(AppValue::String(s)) = find_child(fields, "listofdlc") {
                        for part in s.split(',') {
                            if let Ok(dlc_id) = part.trim().parse::<u32>() {
                                dlcs.push(dlc_id);
                            }
                        }
                    }
                }
            }
        }
        dlcs
    }
}

#[derive(Debug, Clone)]
pub enum AppValue {
    Section(Vec<(String, AppValue)>),
    String(String),
    Int32(i32),
    Int64(i64),
}

fn find_child<'a>(items: &'a [(String, AppValue)], name: &str) -> Option<&'a AppValue> {
    for (k, v) in items {
        if k.eq_ignore_ascii_case(name) {
            return Some(v);
        }
    }
    None
}

fn parse_indexed_bkv(
    d: &[u8],
    names: &[String],
    off: &mut usize,
    end: usize,
) -> Result<(Vec<(String, AppValue)>, usize), AppInfoError> {
    let mut out = Vec::new();
    while *off < end {
        let t = d[*off];
        *off += 1;
        if t == 0x08 {
            return Ok((out, *off));
        }
        if *off + 4 > end {
            return Ok((out, *off));
        }

        let idx = Cursor::new(&d[*off..*off + 4])
            .read_u32::<LittleEndian>()
            .map_err(|_| AppInfoError::ParseError(*off))? as usize;
        *off += 4;

        let key = if idx < names.len() {
            names[idx].clone()
        } else {
            format!("?{}", idx)
        };

        match t {
            0x00 => {
                let (kids, _) = parse_indexed_bkv(d, names, off, end)?;
                out.push((key, AppValue::Section(kids)));
            }
            0x01 => {
                let stop = d[*off..]
                    .iter()
                    .position(|&b| b == 0)
                    .ok_or(AppInfoError::ParseError(*off))?;
                let val = String::from_utf8_lossy(&d[*off..*off + stop]).to_string();
                *off += stop + 1;
                out.push((key, AppValue::String(val)));
            }
            0x02 => {
                let val = Cursor::new(&d[*off..*off + 4])
                    .read_i32::<LittleEndian>()
                    .map_err(|_| AppInfoError::ParseError(*off))?;
                *off += 4;
                out.push((key, AppValue::Int32(val)));
            }
            0x07 => {
                let val = Cursor::new(&d[*off..*off + 8])
                    .read_i64::<LittleEndian>()
                    .map_err(|_| AppInfoError::ParseError(*off))?;
                *off += 8;
                out.push((key, AppValue::Int64(val)));
            }
            _ => {
                return Err(AppInfoError::ParseError(*off - 1));
            }
        }
    }
    Ok((out, *off))
}
