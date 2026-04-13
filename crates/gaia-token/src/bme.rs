//! Burn-and-Mint Equilibrium ledger.
//! net circulating = genesis_supply - total_burned + total_minted

use gaia_core::{GaiaError, TokenAmount};
use serde::{Deserialize, Serialize};

pub const GENESIS_SUPPLY_UGAIA: u64 = 21_000_000 * 1_000_000;

#[derive(Clone, Serialize, Deserialize, Debug, Default)]
pub struct BurnMintLedger {
    pub total_burned_ugaia: u64,
    pub total_minted_ugaia: u64,
}

impl BurnMintLedger {
    pub fn new() -> Self { Self::default() }

    pub fn burn(&mut self, amount: TokenAmount) {
        self.total_burned_ugaia += amount.as_ugaia();
    }

    pub fn mint(&mut self, amount: TokenAmount) -> Result<(), GaiaError> {
        self.total_minted_ugaia = self.total_minted_ugaia
            .checked_add(amount.as_ugaia())
            .ok_or_else(|| GaiaError::ValidationFailed("Mint overflow".into()))?;
        Ok(())
    }

    pub fn circulating_supply(&self) -> u64 {
        GENESIS_SUPPLY_UGAIA
            .saturating_sub(self.total_burned_ugaia)
            .saturating_add(self.total_minted_ugaia)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn burn_reduces_supply() {
        let mut l = BurnMintLedger::new();
        l.burn(TokenAmount::from_gaia(1000));
        assert_eq!(l.circulating_supply(), GENESIS_SUPPLY_UGAIA - 1_000_000_000);
    }
    #[test] fn mint_increases_supply() {
        let mut l = BurnMintLedger::new();
        l.burn(TokenAmount::from_gaia(1000));
        l.mint(TokenAmount::from_gaia(500)).unwrap();
        assert_eq!(l.circulating_supply(), GENESIS_SUPPLY_UGAIA - 500_000_000);
    }
}
