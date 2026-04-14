use gaia_core::TokenAmount;
use serde::{Deserialize, Serialize};

#[derive(Clone, PartialEq, Eq, Serialize, Deserialize, Debug)]
pub enum VestingType {
    /// 50% immediate + 50% linear over 90 days (miner rewards).
    MinerReward,
    /// Linear over 5 years (genesis ceremony participants).
    GenesisParticipant,
    /// Unlocked at genesis (ecosystem fund).
    Immediate,
}

#[derive(Clone, Serialize, Deserialize, Debug)]
pub struct VestingSchedule {
    pub vesting_type: VestingType,
    pub total_ugaia: u64,
    pub start_block: u64,
}

impl VestingSchedule {
    /// Calculate unlocked amount at a given block. blocks_per_day typically ~7200.
    pub fn unlocked_at(&self, current_block: u64, blocks_per_day: u64) -> TokenAmount {
        match self.vesting_type {
            VestingType::Immediate => TokenAmount::from_ugaia(self.total_ugaia),
            VestingType::MinerReward => {
                let immediate = self.total_ugaia / 2;
                let vest_half = self.total_ugaia - immediate;
                let elapsed = current_block.saturating_sub(self.start_block);
                let vest_blocks = 90 * blocks_per_day;
                let vested = (vest_half as u128 * elapsed.min(vest_blocks) as u128 / vest_blocks as u128) as u64;
                TokenAmount::from_ugaia(immediate + vested)
            }
            VestingType::GenesisParticipant => {
                let elapsed = current_block.saturating_sub(self.start_block);
                let vest_blocks = 5 * 365 * blocks_per_day;
                let vested = (self.total_ugaia as u128 * elapsed.min(vest_blocks) as u128 / vest_blocks as u128) as u64;
                TokenAmount::from_ugaia(vested)
            }
        }
    }
}
