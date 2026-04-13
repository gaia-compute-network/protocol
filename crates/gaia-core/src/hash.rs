use sha2::{Digest, Sha256};
use serde::{Deserialize, Serialize};
use std::fmt;

/// A SHA-256 hash used for oracle model weight commitments and task IDs.
#[derive(Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct Hash256([u8; 32]);

impl Hash256 {
    pub fn of(data: &[u8]) -> Self {
        let mut hasher = Sha256::new();
        hasher.update(data);
        Self(hasher.finalize().into())
    }
    pub fn from_bytes(bytes: [u8; 32]) -> Self { Self(bytes) }
    pub fn as_bytes(&self) -> &[u8; 32] { &self.0 }
    pub fn to_hex(&self) -> String { hex::encode(self.0) }
    pub fn from_hex(s: &str) -> Result<Self, hex::FromHexError> {
        let bytes = hex::decode(s)?;
        let mut arr = [0u8; 32];
        arr.copy_from_slice(&bytes);
        Ok(Self(arr))
    }
}

impl fmt::Display for Hash256 {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result { write!(f, "{}", self.to_hex()) }
}
impl fmt::Debug for Hash256 {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result { write!(f, "Hash256({})", self.to_hex()) }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn round_trip_hex() {
        let h = Hash256::of(b"gaia protocol genesis");
        assert_eq!(h, Hash256::from_hex(&h.to_hex()).unwrap());
    }
    #[test]
    fn deterministic() {
        assert_eq!(Hash256::of(b"same"), Hash256::of(b"same"));
    }
}
