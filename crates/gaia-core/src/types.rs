use crate::hash::Hash256;
use serde::{Deserialize, Serialize};
use std::fmt;

#[derive(Clone, PartialEq, Eq, Hash, Serialize, Deserialize, Debug)]
pub struct NodeId(Hash256);
impl NodeId {
    pub fn from_public_key(pubkey: &[u8]) -> Self { Self(Hash256::of(pubkey)) }
}
impl fmt::Display for NodeId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result { write!(f, "node:{}", self.0) }
}

#[derive(Clone, PartialEq, Eq, Serialize, Deserialize, Debug)]
pub enum NodeType { Compute, Validator, Oracle }

/// Token amount in micro-GAIA (1 GAIA = 1_000_000 uGAIA). Max supply = 21M GAIA.
#[derive(Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize, Debug)]
pub struct TokenAmount(u64);
impl TokenAmount {
    pub const ZERO: Self = Self(0);
    pub const MAX_SUPPLY: Self = Self(21_000_000 * 1_000_000);
    pub fn from_gaia(g: u64) -> Self { Self(g * 1_000_000) }
    pub fn from_ugaia(u: u64) -> Self { Self(u) }
    pub fn as_ugaia(self) -> u64 { self.0 }
    pub fn checked_add(self, rhs: Self) -> Option<Self> { self.0.checked_add(rhs.0).map(Self) }
    pub fn checked_sub(self, rhs: Self) -> Option<Self> { self.0.checked_sub(rhs.0).map(Self) }
}
impl fmt::Display for TokenAmount {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let (g, fr) = (self.0 / 1_000_000, self.0 % 1_000_000);
        if fr == 0 { write!(f, "{g} GAIA") } else { write!(f, "{g}.{fr:06} GAIA") }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn max_supply() { assert_eq!(TokenAmount::MAX_SUPPLY.as_ugaia(), 21_000_000_000_000); }
    #[test] fn display() { assert_eq!(TokenAmount::from_gaia(1).to_string(), "1 GAIA"); }
}
