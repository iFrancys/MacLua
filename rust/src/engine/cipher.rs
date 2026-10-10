//! Steam chunk decryption pipeline: AES-256-ECB IV derivation and AES-256-CBC with PKCS7.

use aes::cipher::{BlockDecrypt, BlockDecryptMut, KeyInit, KeyIvInit};
use aes::Aes256;
use cbc::Decryptor;

#[derive(Debug, thiserror::Error)]
pub enum CipherError {
    #[error("depot key must be 32 bytes")]
    InvalidKeyLength,
    #[error("cipher length must be >= 32 and a multiple of 16, got {0}")]
    InvalidCipherLength(usize),
    #[error("invalid PKCS7 padding")]
    InvalidPadding,
}

/// Decrypts a Steam depot chunk according to Valve's specification:
/// 1. `iv = AES256-ECB_Decrypt(key, cipher[0..16])`
/// 2. `plaintext = AES256-CBC_Decrypt(key, iv, cipher[16..])` with PKCS7 unpadding.
pub fn decrypt_chunk(cipher_text: &[u8], key: &[u8]) -> Result<Vec<u8>, CipherError> {
    if key.len() != 32 {
        return Err(CipherError::InvalidKeyLength);
    }
    if cipher_text.len() < 32 || cipher_text.len() % 16 != 0 {
        return Err(CipherError::InvalidCipherLength(cipher_text.len()));
    }

    // Step 1: Derive IV by ECB-decrypting the first 16 bytes
    let cipher_block = Aes256::new(key.into());
    let mut iv = [0u8; 16];
    iv.copy_from_slice(&cipher_text[..16]);
    let mut block = aes::Block::from(iv);
    cipher_block.decrypt_block(&mut block);
    let iv_derived: [u8; 16] = block.into();

    // Step 2: CBC decrypt remaining payload with derived IV
    let cbc_decryptor = Decryptor::<Aes256>::new(key.into(), &iv_derived.into());
    let mut buf = cipher_text[16..].to_vec();
    let plain = cbc_decryptor
        .decrypt_padded_mut::<aes::cipher::block_padding::Pkcs7>(&mut buf)
        .map_err(|_| CipherError::InvalidPadding)?;

    Ok(plain.to_vec())
}

/// Encrypts a plaintext chunk for testing and roundtrip verification.
#[cfg(test)]
pub fn encrypt_chunk_for_test(plain_text: &[u8], key: &[u8], raw_iv_seed: &[u8; 16]) -> Vec<u8> {
    use aes::cipher::{BlockEncrypt, BlockEncryptMut};
    use cbc::Encryptor;

    // ECB encrypt the raw_iv_seed to create the first 16 bytes of the chunk
    let cipher_block = Aes256::new(key.into());
    let mut ecb_block = aes::Block::from(*raw_iv_seed);
    cipher_block.encrypt_block(&mut ecb_block);
    let first_16: [u8; 16] = ecb_block.into();

    // CBC encrypt the plaintext using raw_iv_seed as IV
    let cbc_encryptor = Encryptor::<Aes256>::new(key.into(), raw_iv_seed.into());
    let mut buf = vec![0u8; plain_text.len() + 16];
    let encrypted = cbc_encryptor
        .encrypt_padded_b2b_mut::<aes::cipher::block_padding::Pkcs7>(plain_text, &mut buf)
        .expect("encryption failed");

    let mut out = Vec::with_capacity(16 + encrypted.len());
    out.extend_from_slice(&first_16);
    out.extend_from_slice(encrypted);
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_roundtrip_decrypt() {
        let key = [0x42u8; 32];
        let raw_iv = [0x11u8; 16];
        let original_data = b"Steam chunk data to encrypt and decrypt with PKCS7";

        let encrypted = encrypt_chunk_for_test(original_data, &key, &raw_iv);
        let decrypted = decrypt_chunk(&encrypted, &key).expect("decryption failed");
        assert_eq!(decrypted, original_data);
    }

    #[test]
    fn test_invalid_length() {
        let key = [0x42u8; 32];
        assert!(decrypt_chunk(&[0u8; 15], &key).is_err());
        assert!(decrypt_chunk(&[0u8; 31], &key).is_err());
    }
}
