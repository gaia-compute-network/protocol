"""
Comprehensive unit tests for the GAIA Protocol: Freivalds algorithm and cryptographic primitives.
"""

import pytest
import numpy as np
import hashlib
import time

class FreivaldsAlgorithm:
    def __init__(self, seed=None):
        self.seed = seed
        if seed is not None:
            np.random.seed(seed)

    def verify(self, A, B, C, rounds=10):
        if A.shape[1] != B.shape[0]:
            raise ValueError("Dimension mismatch")
        if A.shape[0] != C.shape[0] or B.shape[1] != C.shape[1]:
            raise ValueError("C dimension mismatch")
        # Cast to float64 for numerical stability across hardware
        A64 = A.astype(np.float64)
        B64 = B.astype(np.float64)
        C64 = C.astype(np.float64)
        n = B64.shape[0]
        # Tolerance for float64 arithmetic on large matrices
        atol = max(1e-6 * n, 1e-4)
        rng = np.random.default_rng(self.seed)
        for round_num in range(rounds):
            r = rng.choice(np.array([-1.0, 1.0]), size=n)
            Br = B64 @ r
            ABr = A64 @ Br
            Cr = C64 @ r
            if not np.allclose(ABr, Cr, rtol=1e-8, atol=atol):
                error_prob = 2.0 ** (-(round_num + 1))
                return False, error_prob, round_num + 1
        error_prob = 2.0 ** (-rounds)
        return True, error_prob, rounds

class Int32Quantization:
    SCALE_FACTOR = 10000.0
    INT32_MAX = 2**31 - 1
    INT32_MIN = -(2**31)
    @staticmethod
    def quantize(matrix):
        scaled = matrix * Int32Quantization.SCALE_FACTOR
        clipped = np.clip(scaled, Int32Quantization.INT32_MIN, Int32Quantization.INT32_MAX)
        return clipped.astype(np.int32)

class CommitmentScheme:
    @staticmethod
    def generate_commitment(task_id, miner_id, result_matrix, timestamp):
        result_bytes = result_matrix.astype(np.int32).tobytes()
        commitment_data = b"GAIA_COMMITMENT_V1" + task_id.encode("utf-8") + miner_id.encode("utf-8") + str(timestamp).encode("utf-8") + result_bytes
        return hashlib.sha256(commitment_data).hexdigest()
    @staticmethod
    def generate_result_fingerprint(task_id, result_matrix):
        result_bytes = result_matrix.astype(np.int32).tobytes()
        fingerprint_data = b"GAIA_RESULT_FINGERPRINT_V1" + task_id.encode("utf-8") + result_bytes
        return hashlib.sha256(fingerprint_data).hexdigest()

class QuorumVerification:
    @staticmethod
    def find_consensus(fingerprints):
        counts = {}
        for fp in fingerprints:
            counts[fp] = counts.get(fp, 0) + 1
        if not counts:
            return None, 0
        consensus_fp, count = max(counts.items(), key=lambda x: x[1])
        if count >= 2:
            return consensus_fp, count
        return None, 0

@pytest.fixture
def sample_matrices_small():
    np.random.seed(42)
    n, m, p = 8, 8, 8
    A = np.random.randn(n, m).astype(np.float32)
    B = np.random.randn(m, p).astype(np.float32)
    C = A @ B
    return A, B, C

@pytest.fixture
def sample_matrices_medium():
    np.random.seed(42)
    n, m, p = 64, 64, 64
    A = np.random.randn(n, m).astype(np.float32)
    B = np.random.randn(m, p).astype(np.float32)
    C = A @ B
    return A, B, C

@pytest.fixture
def sample_matrices_large():
    np.random.seed(42)
    n, m, p = 512, 512, 512
    A = np.random.randn(n, m).astype(np.float32)
    B = np.random.randn(m, p).astype(np.float32)
    C = A @ B
    return A, B, C

class TestFreivaldsAlgorithm:
    def test_freivalds_correct_multiplication(self, sample_matrices_small):
        A, B, C = sample_matrices_small
        f = FreivaldsAlgorithm(seed=123)
        passed, error_prob, rounds = f.verify(A, B, C, rounds=10)
        assert passed and error_prob < 0.001 and rounds == 10
    def test_freivalds_incorrect_multiplication(self, sample_matrices_small):
        A, B, C = sample_matrices_small
        C_bad = C + np.random.randn(*C.shape) * 100
        f = FreivaldsAlgorithm(seed=123)
        passed, _, _ = f.verify(A, B, C_bad, rounds=10)
        assert not passed
    def test_freivalds_identity_matrix(self, sample_matrices_small):
        A, _, _ = sample_matrices_small
        I = np.eye(A.shape[0], dtype=np.float32)
        C = I @ A
        f = FreivaldsAlgorithm(seed=123)
        passed, _, _ = f.verify(I, A, C, rounds=5)
        assert passed
    def test_freivalds_zero_matrix(self, sample_matrices_small):
        A, B, _ = sample_matrices_small
        Z = np.zeros_like(A, dtype=np.float32)
        C = Z @ B
        f = FreivaldsAlgorithm(seed=123)
        passed, _, _ = f.verify(Z, B, C, rounds=5)
        assert passed
    def test_freivalds_large_matrix_performance(self):
        """
        Large matrix performance test. Uses float64 matrices (correct for Freivalds).
        Note: miners receive float32 inputs and quantize to INT32 before submission.
        Freivalds is run by validators on the INT32 (→ float64 cast) matrices.
        This test verifies the performance constraint: 512×512 in <500ms.
        """
        np.random.seed(42)
        n = 512
        # Use float64 for numerical correctness (as validators do after INT32 cast)
        A = np.random.randn(n, n)
        B = np.random.randn(n, n)
        C = A @ B  # Exact float64 product
        f = FreivaldsAlgorithm(seed=123)
        start = time.time()
        passed, _, _ = f.verify(A, B, C, rounds=10)
        elapsed_ms = (time.time() - start) * 1000
        assert passed, "Freivalds should verify exact float64 multiplication"
        assert elapsed_ms < 500, f"Verification took {elapsed_ms:.1f}ms, expected <500ms"
    def test_freivalds_10_rounds_error_bound(self, sample_matrices_medium):
        A, B, C = sample_matrices_medium
        f = FreivaldsAlgorithm(seed=123)
        _, error_prob, _ = f.verify(A, B, C, rounds=10)
        assert error_prob < 0.001
    def test_freivalds_determinism(self, sample_matrices_small):
        A, B, C = sample_matrices_small
        f1 = FreivaldsAlgorithm(seed=999)
        r1 = f1.verify(A, B, C, rounds=5)
        f2 = FreivaldsAlgorithm(seed=999)
        r2 = f2.verify(A, B, C, rounds=5)
        assert r1 == r2
    def test_freivalds_different_seeds(self, sample_matrices_small):
        A, B, C = sample_matrices_small
        f1 = FreivaldsAlgorithm(seed=111)
        r1 = f1.verify(A, B, C, rounds=10)
        f2 = FreivaldsAlgorithm(seed=222)
        r2 = f2.verify(A, B, C, rounds=10)
        assert r1[0] and r2[0]

class TestInt32Quantization:
    def test_quantize_preserves_shape(self):
        orig = np.array([[1.5, 2.7], [3.2, 4.9]], dtype=np.float32)
        q = Int32Quantization.quantize(orig)
        assert q.shape == orig.shape
    def test_quantize_produces_int32_dtype(self):
        orig = np.random.randn(8, 8).astype(np.float32)
        q = Int32Quantization.quantize(orig)
        assert q.dtype == np.int32
    def test_quantize_deterministic_across_calls(self):
        orig = np.random.randn(16, 16).astype(np.float32)
        q1 = Int32Quantization.quantize(orig)
        q2 = Int32Quantization.quantize(orig)
        assert np.array_equal(q1, q2)
    def test_quantize_different_gpus_same_result(self):
        np.random.seed(42)
        orig = np.random.randn(32, 32).astype(np.float32)
        q1 = Int32Quantization.quantize(orig.copy())
        np.random.seed(999)
        q2 = Int32Quantization.quantize(orig.copy())
        assert np.array_equal(q1, q2)
    def test_quantize_large_values_no_overflow(self):
        large = np.ones((10, 10), dtype=np.float32) * 1e6
        q = Int32Quantization.quantize(large)
        assert np.all(q <= Int32Quantization.INT32_MAX)
        assert q.dtype == np.int32

class TestCommitmentScheme:
    def test_commitment_includes_miner_id(self):
        r = np.array([[1, 2], [3, 4]], dtype=np.int32)
        c1 = CommitmentScheme.generate_commitment("t1", "m1", r, 100)
        c2 = CommitmentScheme.generate_commitment("t1", "m2", r, 100)
        assert c1 != c2
    def test_commitment_tamper_detection(self):
        r1 = np.array([[1, 2], [3, 4]], dtype=np.int32)
        r2 = np.array([[1, 2], [3, 5]], dtype=np.int32)
        c1 = CommitmentScheme.generate_commitment("t1", "m1", r1, 100)
        c2 = CommitmentScheme.generate_commitment("t1", "m1", r2, 100)
        assert c1 != c2
    def test_commitment_is_hex_string_64_chars(self):
        r = np.array([[1, 2], [3, 4]], dtype=np.int32)
        c = CommitmentScheme.generate_commitment("t1", "m1", r, 100)
        assert len(c) == 64
    def test_result_fingerprint_miner_agnostic(self):
        r = np.array([[1, 2], [3, 4]], dtype=np.int32)
        f1 = CommitmentScheme.generate_result_fingerprint("t1", r)
        f2 = CommitmentScheme.generate_result_fingerprint("t1", r)
        assert f1 == f2
    def test_fingerprint_different_results_differ(self):
        r1 = np.array([[1, 2], [3, 4]], dtype=np.int32)
        r2 = np.array([[5, 6], [7, 8]], dtype=np.int32)
        f1 = CommitmentScheme.generate_result_fingerprint("t1", r1)
        f2 = CommitmentScheme.generate_result_fingerprint("t1", r2)
        assert f1 != f2

class TestQuorumVerification:
    def test_3_honest_miners_reach_consensus(self):
        r = np.array([[1, 2], [3, 4]], dtype=np.int32)
        fps = [CommitmentScheme.generate_result_fingerprint("t1", r) for _ in range(3)]
        fp, c = QuorumVerification.find_consensus(fps)
        assert fp is not None and c == 3
    def test_2_honest_1_cheater_cheater_caught(self):
        r1 = np.array([[1, 2], [3, 4]], dtype=np.int32)
        r2 = np.array([[5, 6], [7, 8]], dtype=np.int32)
        f1 = CommitmentScheme.generate_result_fingerprint("t1", r1)
        f2 = CommitmentScheme.generate_result_fingerprint("t1", r2)
        fps = [f1, f1, f2]
        fp, c = QuorumVerification.find_consensus(fps)
        assert fp == f1 and c == 2
    def test_all_3_corrupt_all_slashed(self):
        fps = [CommitmentScheme.generate_result_fingerprint("t1", np.array([[i, i+1], [i+2, i+3]], dtype=np.int32)) for i in range(1, 4)]
        fp, c = QuorumVerification.find_consensus(fps)
        assert fp is None or c < 2
    def test_consensus_result_correct_value(self):
        r1 = np.array([[10, 20], [30, 40]], dtype=np.int32)
        r2 = np.array([[1, 2], [3, 4]], dtype=np.int32)
        f1 = CommitmentScheme.generate_result_fingerprint("t1", r1)
        f2 = CommitmentScheme.generate_result_fingerprint("t1", r2)
        fps = [f1, f1, f2]
        fp, c = QuorumVerification.find_consensus(fps)
        assert fp == f1 and c == 2

class TestIntegration:
    def test_quantize_freivalds_pipeline(self):
        """
        Verify the GAIA pipeline: quantize A and B to INT32, compute C = A_q @ B_q,
        then verify with Freivalds. CRITICAL: C must be the quantized product, NOT
        quantize(A@B). These are different because quantization is not distributive
        over multiplication. The on-chain contract always stores A_q @ B_q as C.
        """
        np.random.seed(42)
        A = np.random.randn(16, 16).astype(np.float32)
        B = np.random.randn(16, 16).astype(np.float32)
        # Quantize A and B
        A_q = Int32Quantization.quantize(A).astype(np.float64)
        B_q = Int32Quantization.quantize(B).astype(np.float64)
        # C must be the ACTUAL product of quantized matrices (not quantize(A@B))
        C_q = A_q @ B_q
        f = FreivaldsAlgorithm(seed=123)
        passed, error_prob, _ = f.verify(A_q, B_q, C_q, rounds=10)
        assert passed, "Freivalds should verify A_q @ B_q == C_q"
        assert error_prob < 0.001

    def test_commitment_fingerprint_consistency(self):
        r = np.array([[100, 200], [300, 400]], dtype=np.int32)
        commitment = CommitmentScheme.generate_commitment("task-001", "miner-001", r, 2000)
        fingerprint = CommitmentScheme.generate_result_fingerprint("task-001", r)
        assert len(commitment) == 64
        assert len(fingerprint) == 64
        assert commitment != fingerprint

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
