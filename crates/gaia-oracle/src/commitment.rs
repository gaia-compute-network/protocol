use gaia_core::{GaiaError, Hash256};
use serde::{Deserialize, Serialize};

#[derive(Clone, Serialize, Deserialize, Debug)]
pub struct OracleConfig {
    pub genesis_model_hash: Hash256,
    pub genesis_block: u64,
    pub ceremony_participants: usize,
    pub ceremony_countries: usize,
}
impl OracleConfig {
    pub fn validate(&self) -> Result<(), GaiaError> {
        if self.ceremony_participants < 9 {
            return Err(GaiaError::ValidationFailed(format!(">=9 participants required, got {}", self.ceremony_participants)));
        }
        if self.ceremony_countries < 5 {
            return Err(GaiaError::ValidationFailed(format!(">=5 countries required, got {}", self.ceremony_countries)));
        }
        Ok(())
    }
}

pub struct ModelCommitment { config: OracleConfig }
impl ModelCommitment {
    pub fn new(config: OracleConfig) -> Result<Self, GaiaError> {
        config.validate()?;
        Ok(Self { config })
    }
    pub fn verify_weights(&self, weights: &[u8]) -> Result<bool, GaiaError> {
        Ok(Hash256::of(weights) == self.config.genesis_model_hash)
    }
    pub fn genesis_hash(&self) -> &Hash256 { &self.config.genesis_model_hash }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn cfg() -> OracleConfig {
        OracleConfig { genesis_model_hash: Hash256::of(b"weights"), genesis_block: 0, ceremony_participants: 9, ceremony_countries: 5 }
    }
    #[test] fn correct_weights_pass() { assert!(ModelCommitment::new(cfg()).unwrap().verify_weights(b"weights").unwrap()); }
    #[test] fn tampered_weights_fail() { assert!(!ModelCommitment::new(cfg()).unwrap().verify_weights(b"tampered").unwrap()); }
    #[test] fn too_few_participants() { let mut c = cfg(); c.ceremony_participants = 7; assert!(ModelCommitment::new(c).is_err()); }
}
