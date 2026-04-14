use gaia_core::{GaiaError, NodeId, NodeType, TokenAmount};
use std::collections::HashMap;

#[derive(Clone, Debug)]
pub struct NodeInfo {
    pub id: NodeId,
    pub node_type: NodeType,
    pub collateral: TokenAmount,
    pub available: bool,
}

pub struct NodeRegistry { nodes: HashMap<String, NodeInfo> }

impl NodeRegistry {
    pub fn new() -> Self { Self { nodes: HashMap::new() } }
    pub fn register(&mut self, info: NodeInfo) { self.nodes.insert(info.id.to_string(), info); }
    pub fn available_compute_nodes(&self) -> Vec<&NodeInfo> {
        self.nodes.values().filter(|n| n.node_type == NodeType::Compute && n.available).collect()
    }
}
impl Default for NodeRegistry { fn default() -> Self { Self::new() } }

pub struct Router { registry: NodeRegistry }

impl Router {
    pub fn new(registry: NodeRegistry) -> Self { Self { registry } }
    /// Select a compute node for assignment (round-robin stub).
    pub fn assign(&self) -> Result<NodeId, GaiaError> {
        self.registry
            .available_compute_nodes()
            .first()
            .map(|n| n.id.clone())
            .ok_or_else(|| GaiaError::NodeNotFound("No available compute nodes".into()))
    }
}
