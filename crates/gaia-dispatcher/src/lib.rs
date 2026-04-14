//! # gaia-dispatcher
//!
//! Task routing, priority queuing, and compute node assignment.
//! Receives tasks from ingestion, matches to compute nodes by hardware,
//! and tracks lifecycle from submission to completion.

pub mod queue;
pub mod router;

pub use queue::{PriorityQueue, QueuedTask};
pub use router::{NodeInfo, NodeRegistry, Router};
