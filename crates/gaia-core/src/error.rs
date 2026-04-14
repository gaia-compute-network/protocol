use thiserror::Error;

#[derive(Error, Debug)]
pub enum GaiaError {
    #[error("Invalid task: {0}")]
    InvalidTask(String),
    #[error("Validation failed: {0}")]
    ValidationFailed(String),
    #[error("Oracle mismatch: expected {expected}, got {actual}")]
    OracleMismatch { expected: String, actual: String },
    #[error("Quorum not reached: {validators_agreed}/{validators_required}")]
    QuorumNotReached { validators_agreed: usize, validators_required: usize },
    #[error("Node not found: {0}")]
    NodeNotFound(String),
    #[error("Insufficient collateral: required {required}, available {available}")]
    InsufficientCollateral { required: u64, available: u64 },
    #[error("Serialization error: {0}")]
    Serialization(#[from] serde_json::Error),
    #[error("Internal error: {0}")]
    Internal(#[from] anyhow::Error),
}
