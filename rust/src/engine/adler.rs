//! Steam Adler-32 implementation.
//!
//! Unlike standard zlib Adler-32 (which initializes s1=1, s2=0),
//! Steam initializes seeds at s1=0, s2=0.

const BASE: u32 = 65521;
const NMAX: usize = 5552; // Max bytes before s2 might overflow u32

/// Computes the Steam-flavor Adler-32 checksum with initial seeds s1=0, s2=0.
pub fn steam_adler32(data: &[u8]) -> u32 {
    let mut s1: u32 = 0;
    let mut s2: u32 = 0;

    let mut chunks = data.chunks_exact(NMAX);
    for chunk in chunks.by_ref() {
        for &b in chunk {
            s1 += b as u32;
            s2 += s1;
        }
        s1 %= BASE;
        s2 %= BASE;
    }

    let remainder = chunks.remainder();
    for &b in remainder {
        s1 += b as u32;
        s2 += s1;
    }
    s1 %= BASE;
    s2 %= BASE;

    (s2 << 16) | s1
}

#[cfg(test)]
mod tests {
    use super::*;

    // Replicate Python's formula: adler0(data) = (((((a >> 16) - n) % 65521) << 16) | ((a - 1) % 65521))
    fn python_adler0_equivalent(data: &[u8]) -> u32 {
        let n = data.len() as u32;
        let mut s1: u32 = 1;
        let mut s2: u32 = 0;
        for &b in data {
            s1 = (s1 + b as u32) % 65521;
            s2 = (s2 + s1) % 65521;
        }
        let zlib_a = (s2 << 16) | s1;
        let s2_part = (zlib_a >> 16) & 0xFFFF;
        let s1_part = zlib_a & 0xFFFF;

        let py_s2 = (((s2_part as i64 - n as i64).rem_euclid(65521)) as u32) & 0xFFFF;
        let py_s1 = (((s1_part as i64 - 1).rem_euclid(65521)) as u32) & 0xFFFF;
        (py_s2 << 16) | py_s1
    }

    #[test]
    fn test_empty_adler() {
        assert_eq!(steam_adler32(b""), 0);
    }

    #[test]
    fn test_short_data() {
        let data = b"Hello Steam!";
        assert_eq!(steam_adler32(data), python_adler0_equivalent(data));
    }

    #[test]
    fn test_large_data() {
        let data: Vec<u8> = (0..100_000).map(|i| (i * 37) as u8).collect();
        assert_eq!(steam_adler32(&data), python_adler0_equivalent(&data));
    }
}
