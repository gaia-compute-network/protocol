use gaia_core::TokenAmount;
use serde::{Deserialize, Serialize};

#[derive(Clone, PartialEq, Eq, Serialize, Deserialize, Debug)]
pub enum FeeType { TaskSubmission, Compute, Validation }

/// Protocol fee schedule (governable within bounds set by immutable constants).
#[derive(Clone, Serialize, Deserialize, Debug)]
pub struct FeeSchedule {
    /// Per-task submission fee -> protocol treasury. Default: 0.1 GAIA.
    pub task_submission_ugaia: u64,
    /// Per-quorum validation fee split among validators. Default: 0.05 GAIA.
    pub validation_ugaia: u64,
    /// Maximum compute fee per task. Immutable cap: 5 GAIA.
    pub max_compute_ugaia: u64,
}

impl Default for FeeSchedule {
    fn default() -> Self {
        Self { task_submission_ugaia: 100_000, validation_ugaia: 50_000, max_compute_ugaia: 5_000_000 }
    }
}

impl FeeSchedule {
    pub fn task_submission(&self) -> TokenAmount { TokenAmount::from_ugaia(self.task_submission_ugaia) }
    pub fn validation(&self) -> TokenAmount { TokenAmount::from_ugaia(self.validation_ugaia) }
    pub fn validator_share(&self, n: usize) -> TokenAmount {
        TokenAmount::from_ugaia(self.validation_ugaia / n as u64)
    }
}
