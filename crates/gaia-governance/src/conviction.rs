use gaia_core::{NodeId, TokenAmount};
use serde::{Deserialize, Serialize};

/// Conviction multiplier based on prior lock-in periods.
/// Prevents flash attacks: token holder must lock for the full voting period.
#[derive(Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize, Debug)]
pub enum ConvictionMultiplier {
    Level0, // new voter: 1.0x
    Level1, // 1 period locked: 1.5x
    Level2, // 2+ periods: 3.0x
    Level3, // 3+ periods: 6.0x
    Level4, // 4+ periods: capped at 6.0x per spec
}

impl ConvictionMultiplier {
    /// Multiplier * 10 (fixed-point, denominator 10).
    pub fn numerator(self) -> u64 {
        match self { Self::Level0 => 10, Self::Level1 => 15, Self::Level2 => 30, Self::Level3 | Self::Level4 => 60 }
    }
    pub fn from_periods(periods: u32) -> Self {
        match periods { 0 => Self::Level0, 1 => Self::Level1, 2 => Self::Level2, 3 => Self::Level3, _ => Self::Level4 }
    }
}

#[derive(Clone, Serialize, Deserialize, Debug)]
pub struct VotingPower { pub tokens_locked: TokenAmount, pub multiplier: ConvictionMultiplier }

impl VotingPower {
    /// Effective weight in uGAIA-equivalents = tokens * multiplier.
    pub fn effective_weight(&self) -> u64 {
        self.tokens_locked.as_ugaia() * self.multiplier.numerator() / 10
    }
}

#[derive(Clone, Serialize, Deserialize, Debug)]
pub struct ConvictionVote { pub voter: NodeId, pub approve: bool, pub power: VotingPower }

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn level0_is_1x() { assert_eq!(ConvictionMultiplier::Level0.numerator(), 10); }
    #[test] fn level3_is_6x() { assert_eq!(ConvictionMultiplier::Level3.numerator(), 60); }
    #[test] fn level4_capped_at_6x() { assert_eq!(ConvictionMultiplier::Level4.numerator(), 60); }
    #[test] fn voting_power_3x() {
        let vp = VotingPower { tokens_locked: TokenAmount::from_gaia(100), multiplier: ConvictionMultiplier::Level2 };
        assert_eq!(vp.effective_weight(), 300_000_000); // 300 GAIA in uGAIA
    }
}
