use crate::conviction::ConvictionVote;
use gaia_core::GaiaError;
use serde::{Deserialize, Serialize};

#[derive(Clone, Serialize, Deserialize, Debug)]
pub enum ProposalType {
    FeeAdjustment { description: String },
    /// Requires >=90% conviction vote.
    OracleRegistryUpdate { new_source: String },
    TreasuryAllocation { amount_ugaia: u64, recipient: String, purpose: String },
    NetworkParameter { key: String, value: String },
}

impl ProposalType {
    /// Required approval % * 10 (e.g. 510 = 51%, 900 = 90%).
    pub fn threshold(&self) -> u64 {
        match self { Self::OracleRegistryUpdate { .. } => 900, _ => 510 }
    }
}

#[derive(Clone, PartialEq, Eq, Serialize, Deserialize, Debug)]
pub enum ProposalStatus {
    Discussion, // 2 weeks
    Voting,     // 1 week
    TimeLocked, // 1 week before execution
    Executed,
    Rejected,
}

#[derive(Clone, Serialize, Deserialize, Debug)]
pub struct GovernanceProposal {
    pub id: u64,
    pub proposal_type: ProposalType,
    pub status: ProposalStatus,
    pub votes: Vec<ConvictionVote>,
    pub total_supply_ugaia: u64,
}

impl GovernanceProposal {
    pub fn new(id: u64, proposal_type: ProposalType, total_supply_ugaia: u64) -> Self {
        Self { id, proposal_type, status: ProposalStatus::Discussion, votes: Vec::new(), total_supply_ugaia }
    }
    pub fn add_vote(&mut self, vote: ConvictionVote) { self.votes.push(vote); }

    /// Returns Ok(true) if passed, Ok(false) if failed. Quorum: >=10% of supply must vote.
    pub fn tally(&self) -> Result<bool, GaiaError> {
        if self.status != ProposalStatus::Voting {
            return Err(GaiaError::ValidationFailed("Not in voting phase".into()));
        }
        let total_voted: u64 = self.votes.iter().map(|v| v.power.tokens_locked.as_ugaia()).sum();
        if total_voted < self.total_supply_ugaia / 10 { return Ok(false); } // quorum not met
        let approve: u64 = self.votes.iter().filter(|v| v.approve).map(|v| v.power.effective_weight()).sum();
        let total: u64 = self.votes.iter().map(|v| v.power.effective_weight()).sum();
        if total == 0 { return Ok(false); }
        Ok(approve * 1000 / total >= self.proposal_type.threshold())
    }
}
