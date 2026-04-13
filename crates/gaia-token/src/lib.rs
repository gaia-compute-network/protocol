//! # gaia-token
//!
//! GAIA token economics: Burn-and-Mint Equilibrium, miner vesting, fee accounting.
//!
//! Supply: 21,000,000 GAIA (fixed cap).
//! Distribution: 50% miner rewards, 30% ecosystem fund, 20% genesis participants.
//! BME: burns (task fees) -> deflation -> price rise -> mining -> minting -> equilibrium.

pub mod bme;
pub mod fees;
pub mod vesting;

pub use bme::BurnMintLedger;
pub use fees::{FeeSchedule, FeeType};
pub use vesting::{VestingSchedule, VestingType};
