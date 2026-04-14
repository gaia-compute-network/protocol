use gaia_core::Task;
use std::collections::VecDeque;

#[derive(Debug)]
pub struct QueuedTask { pub task: Task, pub priority: u32 }

pub struct PriorityQueue { items: VecDeque<QueuedTask> }

impl PriorityQueue {
    pub fn new() -> Self { Self { items: VecDeque::new() } }
    pub fn push(&mut self, task: Task, priority: u32) {
        let qt = QueuedTask { task, priority };
        let pos = self.items.partition_point(|x| x.priority >= priority);
        self.items.insert(pos, qt);
    }
    pub fn pop(&mut self) -> Option<QueuedTask> { self.items.pop_front() }
    pub fn len(&self) -> usize { self.items.len() }
    pub fn is_empty(&self) -> bool { self.items.is_empty() }
}
impl Default for PriorityQueue { fn default() -> Self { Self::new() } }
