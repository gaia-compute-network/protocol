use gaia_core::GaiaError;
use rand::Rng;
use serde::{Deserialize, Serialize};

pub const DEFAULT_ROUNDS: usize = 40;

#[derive(Clone, PartialEq, Eq, Serialize, Deserialize, Debug)]
pub enum VerificationResult {
    Valid,
    Invalid { failed_at_round: usize },
}

pub struct FreivaldsVerifier { rounds: usize }

impl FreivaldsVerifier {
    pub fn new(rounds: usize) -> Self { Self { rounds } }
    pub fn with_default_rounds() -> Self { Self::new(DEFAULT_ROUNDS) }

    /// Verify C == A*B using Freivalds algorithm. O(n^2) vs O(n^3) for direct.
    pub fn verify(&self, a: &[Vec<f64>], b: &[Vec<f64>], c: &[Vec<f64>]) -> Result<VerificationResult, GaiaError> {
        let n = a.len();
        if n == 0 || b.len() != n || c.len() != n {
            return Err(GaiaError::ValidationFailed("Matrix dimension mismatch".into()));
        }
        let mut rng = rand::thread_rng();
        for round in 0..self.rounds {
            let r: Vec<f64> = (0..n).map(|_| if rng.gen::<bool>() { 1.0 } else { 0.0 }).collect();
            let x = mat_vec(b, &r, n);
            let ax = mat_vec(a, &x, n);
            let cr = mat_vec(c, &r, n);
            if !vec_eq(&ax, &cr) { return Ok(VerificationResult::Invalid { failed_at_round: round }); }
        }
        Ok(VerificationResult::Valid)
    }
}

fn mat_vec(m: &[Vec<f64>], v: &[f64], n: usize) -> Vec<f64> {
    (0..n).map(|i| m[i].iter().zip(v).map(|(a, b)| a * b).sum()).collect()
}
fn vec_eq(a: &[f64], b: &[f64]) -> bool {
    a.iter().zip(b).all(|(x, y)| (x - y).abs() < 1e-9)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn identity(n: usize) -> Vec<Vec<f64>> {
        (0..n).map(|i| (0..n).map(|j| if i == j { 1.0 } else { 0.0 }).collect()).collect()
    }
    #[test] fn identity_passes() {
        let i = identity(4);
        assert_eq!(FreivaldsVerifier::new(20).verify(&i, &i, &i).unwrap(), VerificationResult::Valid);
    }
    #[test] fn detects_error() {
        let i = identity(4);
        let mut bad = i.clone(); bad[0][0] = 99.0;
        assert!(matches!(FreivaldsVerifier::new(20).verify(&i, &i, &bad).unwrap(), VerificationResult::Invalid { .. }));
    }
}
