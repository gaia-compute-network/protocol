use gaia_core::{GaiaError, Hash256, NodeId, TaskId};
use serde::{Deserialize, Serialize};

#[derive(Clone, Serialize, Deserialize, Debug)]
pub struct QuorumConfig { pub min_validators: usize, pub timeout_secs: u64 }
impl Default for QuorumConfig {
    fn default() -> Self { Self { min_validators: 3, timeout_secs: 30 } }
}

#[derive(Clone, Serialize, Deserialize, Debug)]
pub struct QuorumVote {
    pub validator_id: NodeId,
    pub task_id: TaskId,
    pub output_hash: Hash256,
    pub freivalds_passed: bool,
}

pub struct Quorum { config: QuorumConfig, votes: Vec<QuorumVote> }

impl Quorum {
    pub fn new(config: QuorumConfig) -> Self { Self { config, votes: Vec::new() } }
    pub fn add_vote(&mut self, vote: QuorumVote) { self.votes.push(vote); }
    pub fn vote_count(&self) -> usize { self.votes.len() }

    pub fn try_reach_consensus(&self) -> Result<Hash256, GaiaError> {
        if self.votes.len() < self.config.min_validators {
            return Err(GaiaError::QuorumNotReached {
                validators_agreed: self.votes.len(),
                validators_required: self.config.min_validators,
            });
        }
        if !self.votes.iter().all(|v| v.freivalds_passed) {
            return Err(GaiaError::ValidationFailed("Freivalds failure in quorum".into()));
        }
        let first = &self.votes[0].output_hash;
        if !self.votes.iter().all(|v| &v.output_hash == first) {
            return Err(GaiaError::ValidationFailed("Output hash disagreement".into()));
        }
        Ok(first.clone())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn consensus_three_agreeing() {
        let mut q = Quorum::new(QuorumConfig::default());
        let h = Hash256::of(b"output");
        let t = TaskId::from_payload(b"task");
        for i in 0..3u8 {
            q.add_vote(QuorumVote { validator_id: NodeId::from_public_key(&[i]), task_id: t.clone(), output_hash: h.clone(), freivalds_passed: true });
        }
        assert_eq!(q.try_reach_consensus().unwrap(), h);
    }
    #[test] fn no_consensus_below_min() {
        let mut q = Quorum::new(QuorumConfig::default());
        q.add_vote(QuorumVote { validator_id: NodeId::from_public_key(&[1]), task_id: TaskId::from_payload(b"t"), output_hash: Hash256::of(b"o"), freivalds_passed: true });
        assert!(matches!(q.try_reach_consensus(), Err(GaiaError::QuorumNotReached { .. })));
    }
}
