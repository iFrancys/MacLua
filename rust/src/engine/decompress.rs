//! Decompression handlers for Steam chunk formats: VSZa (Zstandard), VZa (raw LZMA1), and Zip.

use std::io::{Cursor, Read};
use byteorder::{LittleEndian, ReadBytesExt};
use crc32fast::Hasher as Crc32Hasher;

#[derive(Debug, thiserror::Error)]
pub enum DecompressError {
    #[error("unknown chunk magic: {0:02x?}")]
    UnknownMagic([u8; 4]),
    #[error("malformed VSZa chunk")]
    MalformedVSZa,
    #[error("malformed VZa chunk: {0}")]
    MalformedVZa(&'static str),
    #[error("zstd decompression failed: {0}")]
    ZstdError(#[from] std::io::Error),
    #[error("lzma decompression failed: {0}")]
    LzmaError(String),
    #[error("zip decompression error: {0}")]
    ZipError(#[from] zip::result::ZipError),
    #[error("crc32 mismatch: expected 0x{expected:08x}, got 0x{actual:08x}")]
    CrcMismatch { expected: u32, actual: u32 },
    #[error("decompressed size mismatch: expected {expected}, got {actual}")]
    SizeMismatch { expected: usize, actual: usize },
}

/// Decompresses a plain chunk based on its magic header:
/// - `VSZa`: Steam Zstandard chunk
/// - `VZa`: Steam LZMA chunk
/// - `PK\x03\x04`: Zip chunk
pub fn decompress_chunk(plain: &[u8]) -> Result<Vec<u8>, DecompressError> {
    if plain.len() < 4 {
        return Err(DecompressError::UnknownMagic([0, 0, 0, 0]));
    }

    if plain.starts_with(b"VSZa") {
        decompress_vsza(plain)
    } else if plain.starts_with(b"VZa") || (plain.starts_with(b"VZ") && plain.len() > 3 && plain[2] == b'a') {
        decompress_vza(plain)
    } else if plain.starts_with(b"PK\x03\x04") {
        decompress_zip(plain)
    } else {
        let mut magic = [0u8; 4];
        magic.copy_from_slice(&plain[..4]);
        Err(DecompressError::UnknownMagic(magic))
    }
}

fn decompress_vsza(plain: &[u8]) -> Result<Vec<u8>, DecompressError> {
    // VSZa header is 8 bytes, footer is 11 bytes ending with "zsv"
    if plain.len() < 8 + 11 || !plain.ends_with(b"zsv") {
        return Err(DecompressError::MalformedVSZa);
    }

    let footer_start = plain.len() - 11;
    let mut cursor = Cursor::new(&plain[footer_start..footer_start + 8]);
    let _ = cursor.read_u32::<LittleEndian>()?;
    let out_size = cursor.read_i32::<LittleEndian>()?;
    if out_size < 0 {
        return Err(DecompressError::MalformedVSZa);
    }

    let payload = &plain[8..footer_start];
    let decompressed = zstd::decode_all(Cursor::new(payload))?;

    let expected_size = out_size as usize;
    if expected_size > 0 && decompressed.len() != expected_size {
        return Err(DecompressError::SizeMismatch {
            expected: expected_size,
            actual: decompressed.len(),
        });
    }

    Ok(decompressed)
}

fn decompress_vza(plain: &[u8]) -> Result<Vec<u8>, DecompressError> {
    // Minimum length check: 7 bytes header + 5 bytes props + 10 bytes footer = 22
    if plain.len() < 7 + 5 + 10 {
        return Err(DecompressError::MalformedVZa("chunk too short"));
    }

    // Check footer magic: last 2 bytes must be 0x767A ('zv')
    let footer_magic = &plain[plain.len() - 2..];
    if footer_magic != b"zv" {
        return Err(DecompressError::MalformedVZa("missing zv footer"));
    }

    // Footer at len - 10: outcrc (u32), outsize (i32)
    let footer_info = &plain[plain.len() - 10..plain.len() - 2];
    let mut cursor = Cursor::new(footer_info);
    let out_crc = cursor.read_u32::<LittleEndian>()?;
    let out_size = cursor.read_i32::<LittleEndian>()?;
    if out_size < 0 {
        return Err(DecompressError::MalformedVZa("negative size in footer"));
    }

    // LZMA props: plain[7..12]
    let props = &plain[7..12];
    let payload = &plain[12..plain.len() - 10];

    // Build standard LZMA header: 5 bytes props + 8 bytes uncompressed size (-1 if unknown)
    let mut lzma_header = Vec::with_capacity(13 + payload.len());
    lzma_header.extend_from_slice(props);
    let uncompressed_len: u64 = if out_size > 0 { out_size as u64 } else { u64::MAX };
    lzma_header.extend_from_slice(&uncompressed_len.to_le_bytes());
    lzma_header.extend_from_slice(payload);

    let mut decompressed = Vec::new();
    lzma_rs::lzma_decompress(&mut Cursor::new(&lzma_header), &mut decompressed)
        .map_err(|e| DecompressError::LzmaError(e.to_string()))?;

    // Post-processing
    let mut result = decompressed;
    if out_size > 0 {
        let expected = out_size as usize;
        if result.len() < expected {
            return Err(DecompressError::MalformedVZa("output shorter than outsize"));
        }
        result.truncate(expected);
    } else if result.len() > 1 {
        // Without out_size, flush padding might add 1 phantom byte
        let mut hasher = Crc32Hasher::new();
        hasher.update(&result);
        if hasher.finalize() != out_crc {
            let mut hasher_trunc = Crc32Hasher::new();
            hasher_trunc.update(&result[..result.len() - 1]);
            if hasher_trunc.finalize() == out_crc {
                result.pop();
            }
        }
    }

    // Final CRC32 check
    let mut final_hasher = Crc32Hasher::new();
    final_hasher.update(&result);
    let final_crc = final_hasher.finalize();
    if final_crc != out_crc {
        return Err(DecompressError::CrcMismatch {
            expected: out_crc,
            actual: final_crc,
        });
    }

    Ok(result)
}

fn decompress_zip(plain: &[u8]) -> Result<Vec<u8>, DecompressError> {
    let reader = Cursor::new(plain);
    let mut archive = zip::ZipArchive::new(reader)?;
    if archive.len() != 1 {
        return Err(DecompressError::MalformedVZa("zip chunk with multiple entries"));
    }
    let mut file = archive.by_index(0)?;
    let mut out = Vec::with_capacity(file.size() as usize);
    file.read_to_end(&mut out)?;
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_vsza_roundtrip() {
        let original = b"Steam Zstandard chunk test data for MacLua Rust engine.";
        let compressed = zstd::encode_all(Cursor::new(original), 3).unwrap();

        let mut vsza = Vec::new();
        vsza.extend_from_slice(b"VSZa");
        vsza.extend_from_slice(&[0u8; 4]); // 4 extra header bytes
        vsza.extend_from_slice(&compressed);
        // Footer: 4 bytes unknown/dummy + 4 bytes outsize (i32) + 3 bytes "zsv"
        vsza.extend_from_slice(&0u32.to_le_bytes());
        vsza.extend_from_slice(&(original.len() as i32).to_le_bytes());
        vsza.extend_from_slice(b"zsv");

        let decompressed = decompress_chunk(&vsza).expect("vsza decompression failed");
        assert_eq!(decompressed, original);
    }

    #[test]
    fn test_zip_chunk() {
        use std::io::Write;
        let original = b"Zip single entry payload";
        let mut buf = Cursor::new(Vec::new());
        {
            let mut zip = zip::ZipWriter::new(&mut buf);
            let options = zip::write::SimpleFileOptions::default()
                .compression_method(zip::CompressionMethod::Deflated);
            zip.start_file("data.bin", options).unwrap();
            zip.write_all(original).unwrap();
            zip.finish().unwrap();
        }

        let zip_bytes = buf.into_inner();
        let decompressed = decompress_chunk(&zip_bytes).expect("zip decompression failed");
        assert_eq!(decompressed, original);
    }
}
