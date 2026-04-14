//! # gaia-oracle
//!
//! Frozen ML oracle: genesis hash commitment and scientific reference verification.
//!
//! At genesis, 9 participants from >=5 countries compute SHA-256 of ML model
//! weights and embed it in the genesis block. This hash is immutable — only a
//! hard fork with >=90% conviction vote can change it.

pub mod commitment;
pub mod reference;

pub use commitment::{ModelCommitment, OracleConfig};
pub use reference::{ReferenceDataset, ReferenceSource, ValidationOutcome};
