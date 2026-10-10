//! Minimal binary VDF reader and serializer for Steam data files (packageinfo.vdf, appinfo.vdf, etc.)
//!
//! Supported node types:
//! - 0x00: Section (nested nodes)
//! - 0x01: String (null-terminated UTF-8)
//! - 0x02: Int32 (4-byte LE)
//! - 0x07: Int64 (8-byte LE)
//! - 0x08: Terminator

use std::io::{Cursor, Write};
use byteorder::{LittleEndian, ReadBytesExt, WriteBytesExt};

#[derive(Debug, Clone, PartialEq)]
pub enum BkvNode {
    Section(String, Vec<BkvNode>),
    String(String, String),
    Int32(String, i32),
    Int64(String, i64),
}

impl BkvNode {
    pub fn key(&self) -> &str {
        match self {
            BkvNode::Section(k, _) => k,
            BkvNode::String(k, _) => k,
            BkvNode::Int32(k, _) => k,
            BkvNode::Int64(k, _) => k,
        }
    }
}

pub struct BkvReader<'a> {
    data: &'a [u8],
    offset: usize,
}

#[derive(Debug, thiserror::Error)]
pub enum BkvError {
    #[error("unexpected end of file at offset 0x{0:x}")]
    UnexpectedEof(usize),
    #[error("string not null-terminated at offset 0x{0:x}")]
    UnterminatedString(usize),
    #[error("unsupported binary VDF type 0x{0:02x} at offset 0x{1:x}")]
    UnsupportedType(u8, usize),
    #[error("I/O error during serialization: {0}")]
    Io(#[from] std::io::Error),
}

impl<'a> BkvReader<'a> {
    pub fn new(data: &'a [u8]) -> Self {
        Self { data, offset: 0 }
    }

    pub fn offset(&self) -> usize {
        self.offset
    }

    pub fn read_u8(&mut self) -> Result<u8, BkvError> {
        if self.offset >= self.data.len() {
            return Err(BkvError::UnexpectedEof(self.offset));
        }
        let b = self.data[self.offset];
        self.offset += 1;
        Ok(b)
    }

    pub fn read_cstr(&mut self) -> Result<String, BkvError> {
        let start = self.offset;
        let end = self.data[start..]
            .iter()
            .position(|&b| b == 0)
            .ok_or(BkvError::UnterminatedString(start))?;
        let s = String::from_utf8_lossy(&self.data[start..start + end]).to_string();
        self.offset = start + end + 1;
        Ok(s)
    }

    pub fn read_i32(&mut self) -> Result<i32, BkvError> {
        if self.offset + 4 > self.data.len() {
            return Err(BkvError::UnexpectedEof(self.offset));
        }
        let mut cur = Cursor::new(&self.data[self.offset..self.offset + 4]);
        self.offset += 4;
        cur.read_i32::<LittleEndian>().map_err(|_| BkvError::UnexpectedEof(self.offset))
    }

    pub fn read_i64(&mut self) -> Result<i64, BkvError> {
        if self.offset + 8 > self.data.len() {
            return Err(BkvError::UnexpectedEof(self.offset));
        }
        let mut cur = Cursor::new(&self.data[self.offset..self.offset + 8]);
        self.offset += 8;
        cur.read_i64::<LittleEndian>().map_err(|_| BkvError::UnexpectedEof(self.offset))
    }

    /// Reads next node. Returns `Ok(None)` when hitting end marker 0x08.
    pub fn parse_node(&mut self) -> Result<Option<BkvNode>, BkvError> {
        let t_offset = self.offset;
        let t = self.read_u8()?;
        if t == 0x08 {
            return Ok(None);
        }

        let key = self.read_cstr()?;
        match t {
            0x00 => {
                let mut children = Vec::new();
                while let Some(child) = self.parse_node()? {
                    children.push(child);
                }
                Ok(Some(BkvNode::Section(key, children)))
            }
            0x01 => {
                let val = self.read_cstr()?;
                Ok(Some(BkvNode::String(key, val)))
            }
            0x02 => {
                let val = self.read_i32()?;
                Ok(Some(BkvNode::Int32(key, val)))
            }
            0x07 => {
                let val = self.read_i64()?;
                Ok(Some(BkvNode::Int64(key, val)))
            }
            _ => Err(BkvError::UnsupportedType(t, t_offset)),
        }
    }
}

/// Serializes a node into binary VDF format.
pub fn ser_node<W: Write>(node: &BkvNode, out: &mut W) -> Result<(), BkvError> {
    match node {
        BkvNode::Section(key, children) => {
            out.write_u8(0x00)?;
            out.write_all(key.as_bytes())?;
            out.write_u8(0x00)?;
            for child in children {
                ser_node(child, out)?;
            }
            out.write_u8(0x08)?;
        }
        BkvNode::String(key, val) => {
            out.write_u8(0x01)?;
            out.write_all(key.as_bytes())?;
            out.write_u8(0x00)?;
            out.write_all(val.as_bytes())?;
            out.write_u8(0x00)?;
        }
        BkvNode::Int32(key, val) => {
            out.write_u8(0x02)?;
            out.write_all(key.as_bytes())?;
            out.write_u8(0x00)?;
            out.write_i32::<LittleEndian>(*val)?;
        }
        BkvNode::Int64(key, val) => {
            out.write_u8(0x07)?;
            out.write_all(key.as_bytes())?;
            out.write_u8(0x00)?;
            out.write_i64::<LittleEndian>(*val)?;
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_bkv_roundtrip() {
        let tree = BkvNode::Section(
            "package0".into(),
            vec![
                BkvNode::String("name".into(), "Free On Demand".into()),
                BkvNode::Int32("packageid".into(), 0),
                BkvNode::Int64("billingtype".into(), 12),
                BkvNode::Section(
                    "appids".into(),
                    vec![
                        BkvNode::Int32("0".into(), 730),
                        BkvNode::Int32("1".into(), 400),
                    ],
                ),
            ],
        );

        let mut buf = Vec::new();
        ser_node(&tree, &mut buf).unwrap();

        let mut reader = BkvReader::new(&buf);
        let parsed = reader.parse_node().unwrap().expect("expected section node");
        assert_eq!(parsed, tree);
    }
}
