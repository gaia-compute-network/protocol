//! # gaia-validator
//!
//! Freivalds-based probabilistic validation and quorum consensus.
//!
//! For k=40 rounds, error probability <= 2^(-40). Minimum 3 validators
//! required. Byzantine fault tolerance: up to 33% malicious nodes tolerated.

pub mod freivalds;
pub mod quorum;

pub use freivalds::{FreivaldsVerifier, VerificationResult};
pub use quorum::{Quorum, QuorumConfig, QuorumVote};
