use crate::hash::Hash256;
use serde::{Deserialize, Serialize};
use std::fmt;

#[derive(Clone, PartialEq, Eq, Hash, Serialize, Deserialize, Debug)]
pub struct TaskId(Hash256);
impl TaskId {
    pub fn new(hash: Hash256) -> Self { Self(hash) }
    pub fn from_payload(payload: &[u8]) -> Self { Self(Hash256::of(payload)) }
}
impl fmt::Display for TaskId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result { write!(f, "task:{}", self.0) }
}

#[derive(Clone, PartialEq, Eq, Serialize, Deserialize, Debug)]
pub enum TaskStatus { Pending, Computing, Validating, Completed, Failed }

#[derive(Clone, Serialize, Deserialize, Debug)]
pub struct Task {
    pub id: TaskId,
    pub model_hash: Hash256,
    pub input_ref: String,
    pub max_fee_ugaia: u64,
    pub status: TaskStatus,
    pub submitted_at_block: u64,
}
impl Task {
    pub fn new(model_hash: Hash256, input_ref: String, max_fee_ugaia: u64, block: u64) -> Self {
        let payload = format!("{model_hash}{input_ref}{max_fee_ugaia}{block}");
        let id = TaskId::from_payload(payload.as_bytes());
        Self { id, model_hash, input_ref, max_fee_ugaia, status: TaskStatus::Pending, submitted_at_block: block }
    }
}

#[derive(Clone, Serialize, Deserialize, Debug)]
pub struct TaskResult {
    pub task_id: TaskId,
    pub output_hash: Hash256,
    pub validators_agreed: usize,
    pub fee_charged_ugaia: u64,
}
