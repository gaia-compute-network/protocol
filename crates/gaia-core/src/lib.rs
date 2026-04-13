//! # gaia-core
//!
//! Core types, traits, and primitives for the GAIA protocol.

pub mod error;
pub mod hash;
pub mod task;
pub mod types;

pub use error::GaiaError;
pub use hash::Hash256;
pub use task::{Task, TaskId, TaskResult, TaskStatus};
pub use types::{NodeId, NodeType, TokenAmount};
