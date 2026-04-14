//! # gaia-governance
//!
//! Conviction voting, COCM anti-collusion, and on-chain parameter governance.
//!
//! ## Governable Parameters
//! - Fee parameters (within bounds)
//! - Oracle registry updates (>=90% conviction required)
//! - Ecosystem fund allocation
//! - Network parameters (quorum size, slash amounts within bounds)
//!
//! ## NOT Governable (immutable constants)
//! - Genesis hash, total supply cap (21M), Burn-and-Mint logic,
//!   time-lock expiry (18mo), validator quorum math, conviction voting structure

pub mod conviction;
pub mod proposal;

pub use conviction::{ConvictionMultiplier, ConvictionVote, VotingPower};
pub use proposal::{GovernanceProposal, ProposalStatus, ProposalType};
