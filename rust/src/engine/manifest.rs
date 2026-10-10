//! Depot manifest parser for Steam Content Manifests.
//!
//! Handles section splitting (magic headers: payload, metadata, signature, terminal)
//! and zero-copy/streaming protobuf field extraction.

use std::path::Path;
use byteorder::{LittleEndian, ReadBytesExt};
use std::io::Cursor;

pub const PAYLOAD_MAGIC: u32 = 0x71F617D0;
pub const METADATA_MAGIC: u32 = 0x1F4812BE;
pub const SIGNATURE_MAGIC: u32 = 0x1B81B817;
pub const TERMINAL_MAGIC: u32 = 0x32C415AB;

pub const FLAG_DIRECTORY: u32 = 0x40;

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct ManifestChunk {
    pub sha: Vec<u8>,
    pub crc: u32,
    pub offset: u64,
    pub cb_original: u32,
    pub cb_compressed: u32,
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct ManifestFileEntry {
    pub name: String,
    pub size: u64,
    pub flags: u32,
    pub sha_content: Option<Vec<u8>>,
    pub link_target: Option<String>,
    pub chunks: Vec<ManifestChunk>,
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct DepotManifest {
    pub depot_id: u32,
    pub gid: u64,
    pub creation_time: Option<u32>,
    pub filenames_encrypted: bool,
    pub files: Vec<ManifestFileEntry>,
    pub raw_size: usize,
}

#[derive(Debug, thiserror::Error)]
pub enum ManifestError {
    #[error("manifest is empty")]
    Empty,
    #[error("truncated manifest section header")]
    TruncatedHeader,
    #[error("manifest section extends beyond end of buffer")]
    SectionOutOfBounds,
    #[error("terminal magic is not at final position")]
    InvalidTerminal,
    #[error("varint too long or truncated")]
    VarintError,
    #[error("unsupported protobuf wire type {0}")]
    UnsupportedWireType(u8),
    #[error("missing required manifest section: {0}")]
    MissingSection(&'static str),
    #[error("filenames in manifest are encrypted")]
    EncryptedFilenames,
    #[error("I/O error reading manifest: {0}")]
    Io(#[from] std::io::Error),
}

/// Splits manifest binary bytes into `(magic, section_payload)` slices.
pub fn split_sections(data: &[u8]) -> Result<Vec<(u32, &[u8])>, ManifestError> {
    if data.is_empty() {
        return Err(ManifestError::Empty);
    }

    let mut sections = Vec::new();
    let mut pos = 0;
    let n = data.len();

    while pos < n {
        if pos + 4 > n {
            return Err(ManifestError::TruncatedHeader);
        }
        let magic = Cursor::new(&data[pos..pos + 4]).read_u32::<LittleEndian>()?;

        if magic == TERMINAL_MAGIC {
            if pos + 4 != n {
                return Err(ManifestError::InvalidTerminal);
            }
            break;
        }

        if pos + 8 > n {
            return Err(ManifestError::TruncatedHeader);
        }
        let length = Cursor::new(&data[pos + 4..pos + 8]).read_u32::<LittleEndian>()? as usize;
        let first = pos + 8;
        let last = first + length;
        if last > n {
            return Err(ManifestError::SectionOutOfBounds);
        }

        sections.push((magic, &data[first..last]));
        pos = last;
    }

    Ok(sections)
}

fn read_varint(buf: &[u8], pos: &mut usize) -> Result<u64, ManifestError> {
    let mut result = 0u64;
    let mut shift = 0;
    while *pos < buf.len() {
        let byte = buf[*pos];
        *pos += 1;
        result |= ((byte & 0x7F) as u64) << shift;
        if (byte & 0x80) == 0 {
            return Ok(result);
        }
        shift += 7;
        if shift >= 70 {
            return Err(ManifestError::VarintError);
        }
    }
    Err(ManifestError::VarintError)
}

#[derive(Debug)]
enum ProtoValue<'a> {
    Varint(u64),
    #[allow(dead_code)]
    Fixed64(u64),
    Bytes(&'a [u8]),
    Fixed32(u32),
}

fn parse_proto_fields<'a>(
    buf: &'a [u8],
) -> impl Iterator<Item = Result<(u32, ProtoValue<'a>), ManifestError>> {
    let mut pos = 0;
    std::iter::from_fn(move || {
        if pos >= buf.len() {
            return None;
        }
        let tag = match read_varint(buf, &mut pos) {
            Ok(t) => t,
            Err(e) => return Some(Err(e)),
        };
        let field = (tag >> 3) as u32;
        let wire = (tag & 7) as u8;

        match wire {
            0 => match read_varint(buf, &mut pos) {
                Ok(v) => Some(Ok((field, ProtoValue::Varint(v)))),
                Err(e) => Some(Err(e)),
            },
            1 => {
                if pos + 8 > buf.len() {
                    return Some(Err(ManifestError::VarintError));
                }
                let val = Cursor::new(&buf[pos..pos + 8])
                    .read_u64::<LittleEndian>()
                    .unwrap();
                pos += 8;
                Some(Ok((field, ProtoValue::Fixed64(val))))
            }
            2 => {
                let len = match read_varint(buf, &mut pos) {
                    Ok(l) => l as usize,
                    Err(e) => return Some(Err(e)),
                };
                if pos + len > buf.len() {
                    return Some(Err(ManifestError::VarintError));
                }
                let slice = &buf[pos..pos + len];
                pos += len;
                Some(Ok((field, ProtoValue::Bytes(slice))))
            }
            5 => {
                if pos + 4 > buf.len() {
                    return Some(Err(ManifestError::VarintError));
                }
                let val = Cursor::new(&buf[pos..pos + 4])
                    .read_u32::<LittleEndian>()
                    .unwrap();
                pos += 4;
                Some(Ok((field, ProtoValue::Fixed32(val))))
            }
            _ => Some(Err(ManifestError::UnsupportedWireType(wire))),
        }
    })
}

fn parse_chunk(buf: &[u8]) -> Result<ManifestChunk, ManifestError> {
    let mut sha = None;
    let mut crc = None;
    let mut offset = None;
    let mut cb_original = None;
    let mut cb_compressed = None;

    for item in parse_proto_fields(buf) {
        let (field, val) = item?;
        match (field, val) {
            (1, ProtoValue::Bytes(b)) => sha = Some(b.to_vec()),
            (2, ProtoValue::Fixed32(c)) => crc = Some(c),
            (3, ProtoValue::Varint(o)) => offset = Some(o),
            (4, ProtoValue::Varint(s)) => cb_original = Some(s as u32),
            (5, ProtoValue::Varint(s)) => cb_compressed = Some(s as u32),
            _ => {}
        }
    }

    Ok(ManifestChunk {
        sha: sha.unwrap_or_default(),
        crc: crc.unwrap_or(0),
        offset: offset.unwrap_or(0),
        cb_original: cb_original.unwrap_or(0),
        cb_compressed: cb_compressed.unwrap_or(0),
    })
}

fn parse_file_entry(buf: &[u8]) -> Result<ManifestFileEntry, ManifestError> {
    let mut name = None;
    let mut size = None;
    let mut flags = 0;
    let mut sha_content = None;
    let mut link_target = None;
    let mut chunks = Vec::new();

    for item in parse_proto_fields(buf) {
        let (field, val) = item?;
        match (field, val) {
            (1, ProtoValue::Bytes(b)) => name = Some(String::from_utf8_lossy(b).to_string()),
            (2, ProtoValue::Varint(s)) => size = Some(s),
            (3, ProtoValue::Varint(f)) => flags = f as u32,
            (5, ProtoValue::Bytes(b)) => sha_content = Some(b.to_vec()),
            (6, ProtoValue::Bytes(b)) => chunks.push(parse_chunk(b)?),
            (7, ProtoValue::Bytes(b)) => link_target = Some(String::from_utf8_lossy(b).to_string()),
            _ => {}
        }
    }

    Ok(ManifestFileEntry {
        name: name.unwrap_or_default(),
        size: size.unwrap_or(0),
        flags,
        sha_content,
        link_target,
        chunks,
    })
}

/// Parses a full depot manifest from memory.
pub fn parse_manifest_bytes(data: &[u8]) -> Result<DepotManifest, ManifestError> {
    let sections = split_sections(data)?;
    let mut payload = None;
    let mut depot_id = None;
    let mut gid = None;
    let mut creation_time = None;
    let mut filenames_encrypted = false;

    for (magic, body) in sections {
        if magic == PAYLOAD_MAGIC {
            payload = Some(body);
        } else if magic == METADATA_MAGIC {
            for item in parse_proto_fields(body) {
                let (field, val) = item?;
                match (field, val) {
                    (1, ProtoValue::Varint(d)) => depot_id = Some(d as u32),
                    (2, ProtoValue::Varint(g)) => gid = Some(g),
                    (3, ProtoValue::Varint(t)) => creation_time = Some(t as u32),
                    (4, ProtoValue::Varint(e)) => filenames_encrypted = e != 0,
                    _ => {}
                }
            }
        }
    }

    let payload = payload.ok_or(ManifestError::MissingSection("payload"))?;
    let depot_id = depot_id.ok_or(ManifestError::MissingSection("depot_id in metadata"))?;
    let gid = gid.ok_or(ManifestError::MissingSection("gid in metadata"))?;

    if filenames_encrypted {
        return Err(ManifestError::EncryptedFilenames);
    }

    let mut files = Vec::new();
    for item in parse_proto_fields(payload) {
        let (field, val) = item?;
        if field == 1 {
            if let ProtoValue::Bytes(b) = val {
                files.push(parse_file_entry(b)?);
            }
        }
    }

    Ok(DepotManifest {
        depot_id,
        gid,
        creation_time,
        filenames_encrypted,
        files,
        raw_size: data.len(),
    })
}

/// Parses a manifest directly from a file path.
pub fn parse_manifest_file<P: AsRef<Path>>(path: P) -> Result<DepotManifest, ManifestError> {
    let data = std::fs::read(path)?;
    parse_manifest_bytes(&data)
}
