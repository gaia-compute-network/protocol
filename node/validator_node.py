"""
GAIA Protocol Validator Node
=============================

A production-grade validator node for the GAIA Protocol that runs Freivalds verification
off-chain and submits results on-chain. Validators are economically incentivized to perform
honest verification because their stake is slashed if they submit false results.

Economic Incentives:
====================
- Validators earn rewards for correctly verifying computation results.
- If a validator submits a false Freivalds result, their stake is slashed by the network.
- The slash amount is significant enough to deter dishonest behavior.
- Any network participant can audit a validator's claimed result by running Freivalds
  independently (it's probabilistic but verifiable).
- This creates a strong Nash equilibrium where honest validation is the dominant strategy.
- The economic design ensures validators have skin in the game and cannot profit from
  lying about whether a computation result is correct.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Tuple
from enum import Enum

import numpy as np

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ValidationStatus(Enum):
    """Enum for validation task statuses."""
    PENDING = "pending"
    VALIDATING = "validating"
    PASSED = "passed"
    FAILED = "failed"
    SUBMITTED = "submitted"


@dataclass
class FreivaldsResult:
    """
    Result of a single Freivalds verification run.

    Freivalds algorithm is a randomized verification algorithm that probabilistically
    checks if C = A * B in O(n^2) time (faster than recomputing the product).
    """
    passed: bool
    rounds: int
    error_probability: float
    elapsed_ms: float
    fingerprint_hash: Optional[str] = None


@dataclass
class ValidatorStats:
    """Statistics tracked by a validator node."""
    tasks_verified: int = 0
    tasks_failed_freivalds: int = 0
    total_rewards_earned: float = 0.0
    slash_events_detected: int = 0
    last_verification_timestamp: Optional[datetime] = None
    uptime_seconds: float = 0.0


class ValidatorNode:
    """
    GAIA Protocol Validator Node.

    Validators receive computation results from miners and verify them using Freivalds.
    They submit verification results on-chain, where incorrect results incur a slash to
    their staked tokens.
    """

    def __init__(
        self,
        validator_id: str,
        stake_address: str,
        rpc_endpoint: str
    ) -> None:
        """
        Initialize a validator node.

        Args:
            validator_id: Unique identifier for this validator
            stake_address: Ethereum-like address where stake is held
            rpc_endpoint: RPC endpoint for blockchain interaction
        """
        self.validator_id = validator_id
        self.stake_address = stake_address
        self.rpc_endpoint = rpc_endpoint

        self.is_running = False
        self.stats = ValidatorStats()

        self._start_time: Optional[float] = None
        self._pending_tasks: dict[str, dict] = {}
        self._verification_queue: asyncio.Queue[str] = asyncio.Queue()

        logger.info(
            f"Validator {validator_id} initialized with stake at {stake_address}"
        )

    async def start(self) -> None:
        """Start the validator node and begin listening for validation tasks."""
        if self.is_running:
            logger.warning(f"Validator {self.validator_id} is already running")
            return

        self.is_running = True
        self._start_time = time.time()
        logger.info(f"Validator {self.validator_id} started")

        # Start background task listener
        asyncio.create_task(self.listen_for_validation_tasks())

    async def stop(self) -> None:
        """Stop the validator node and cleanup resources."""
        if not self.is_running:
            logger.warning(f"Validator {self.validator_id} is not running")
            return

        self.is_running = False

        if self._start_time:
            uptime = time.time() - self._start_time
            self.stats.uptime_seconds = uptime
            logger.info(
                f"Validator {self.validator_id} stopped. Uptime: {uptime:.2f}s"
            )

    async def listen_for_validation_tasks(self) -> None:
        """
        Listen for validation tasks in VALIDATING state.

        In production, this would poll the blockchain or listen to smart contract events.
        This demo version simulates task arrival.
        """
        logger.info(f"Validator {self.validator_id} listening for validation tasks")

        while self.is_running:
            try:
                # In production: query blockchain for tasks in VALIDATING state
                # For demo: wait for tasks added via simulate_task_arrival()
                await asyncio.sleep(2)

                # Process any pending validation tasks
                for task_id in list(self._pending_tasks.keys()):
                    task = self._pending_tasks[task_id]
                    if task.get('status') == ValidationStatus.VALIDATING.value:
                        await self._process_validation_task(task_id)

            except asyncio.CancelledError:
                logger.info(f"Validator {self.validator_id} task listener cancelled")
                break
            except Exception as e:
                logger.error(
                    f"Error in validation task listener: {e}",
                    exc_info=True
                )
                await asyncio.sleep(5)

    async def _process_validation_task(self, task_id: str) -> None:
        """Process a single validation task from start to submission."""
        logger.info(f"Processing validation task {task_id}")

        try:
            # Fetch inputs from IPFS/API
            A, B = await self.fetch_task_inputs(task_id)

            # Fetch the majority result (what miners agreed on)
            C = await self.fetch_majority_result(task_id)

            # Run Freivalds verification with 10 rounds
            result = self.run_freivalds(A, B, C, rounds=10)

            # Submit result on-chain
            await self.submit_freivalds_result(
                task_id,
                result.passed,
                result.fingerprint_hash or "",
                result.rounds
            )

            # Update stats
            self.stats.tasks_verified += 1
            if not result.passed:
                self.stats.tasks_failed_freivalds += 1
            self.stats.last_verification_timestamp = datetime.now()

            logger.info(
                f"Verified task {task_id}: "
                f"passed={result.passed}, "
                f"error_prob={result.error_probability:.6f}"
            )

        except Exception as e:
            logger.error(f"Error processing validation task {task_id}: {e}")

    def run_freivalds(
        self,
        A: np.ndarray,
        B: np.ndarray,
        C: np.ndarray,
        rounds: int = 10
    ) -> FreivaldsResult:
        """
        Run Freivalds probabilistic verification that C = A * B.

        Algorithm:
        For k rounds:
          1. Generate random vector r in {-1, 1}^n
          2. Compute Br
          3. Check if A(Br) == Cr
          4. If any round fails, return False
        If all rounds pass, return True with error probability 2^(-k)

        Time complexity: O(k * n^2) vs O(n^3) for full multiplication.

        Args:
            A: Matrix of shape (n, m)
            B: Matrix of shape (m, p)
            C: Matrix of shape (n, p) - claimed result of A * B
            rounds: Number of verification rounds (default 10)

        Returns:
            FreivaldsResult with verification outcome and statistics
        """
        start_time = time.time()

        # Validate dimensions
        if A.shape[1] != B.shape[0]:
            raise ValueError(
                f"Dimension mismatch: A shape {A.shape}, B shape {B.shape}"
            )
        if A.shape[0] != C.shape[0] or B.shape[1] != C.shape[1]:
            raise ValueError(
                f"C dimension mismatch: expected {A.shape[0]}x{B.shape[1]}, "
                f"got {C.shape}"
            )

        n = B.shape[0]

        # Run k rounds of verification
        for round_num in range(rounds):
            # Generate random vector r in {-1, 1}^n
            r = np.random.choice([-1, 1], size=n)

            # Compute Br (matrix-vector product)
            Br = B @ r

            # Compute A(Br) = A * (B * r)
            ABr = A @ Br

            # Compute Cr (what we expect)
            Cr = C @ r

            # Check if A(Br) == Cr
            if not np.allclose(ABr, Cr, rtol=1e-9, atol=1e-12):
                # Verification failed - the matrices do not match
                error_prob = self.compute_error_probability(round_num + 1)
                elapsed = (time.time() - start_time) * 1000
                return FreivaldsResult(
                    passed=False,
                    rounds=round_num + 1,
                    error_probability=error_prob,
                    elapsed_ms=elapsed,
                    fingerprint_hash=self._hash_matrices(A, B, C)
                )

        # All rounds passed
        elapsed = (time.time() - start_time) * 1000
        error_prob = self.compute_error_probability(rounds)
        return FreivaldsResult(
            passed=True,
            rounds=rounds,
            error_probability=error_prob,
            elapsed_ms=elapsed,
            fingerprint_hash=self._hash_matrices(A, B, C)
        )

    def compute_error_probability(self, rounds: int) -> float:
        """
        Compute the error probability for Freivalds verification.

        If all k rounds pass, the probability that C != A*B is at most 2^(-k).

        Args:
            rounds: Number of rounds completed

        Returns:
            Error probability as a float in [0, 1]
        """
        return 2.0 ** (-rounds)

    async def fetch_task_inputs(self, task_id: str) -> Tuple[np.ndarray, np.ndarray]:
        """
        Fetch task inputs (matrices A and B) from IPFS or API.

        In production, this would retrieve from IPFS using the content hash
        stored in the smart contract.

        Args:
            task_id: Task identifier

        Returns:
            Tuple of (A, B) numpy arrays
        """
        # Demo: generate synthetic matrices
        await asyncio.sleep(0.1)  # Simulate network latency

        n, m, p = 128, 128, 128
        A = np.random.randn(n, m).astype(np.float32)
        B = np.random.randn(m, p).astype(np.float32)

        logger.debug(f"Fetched inputs for task {task_id}: A{A.shape}, B{B.shape}")
        return A, B

    async def fetch_majority_result(self, task_id: str) -> np.ndarray:
        """
        Fetch the majority-agreed result (C) from miners' fingerprints.

        In production, this would reconstruct C from the IPFS hash that achieved
        quorum agreement among miners.

        Args:
            task_id: Task identifier

        Returns:
            The C matrix (result of A * B according to majority)
        """
        # Demo: compute the correct result
        await asyncio.sleep(0.1)  # Simulate network latency

        # Fetch A and B to compute C
        A, B = await self.fetch_task_inputs(task_id)
        C = A @ B

        logger.debug(f"Fetched majority result for task {task_id}: C{C.shape}")
        return C

    async def submit_freivalds_result(
        self,
        task_id: str,
        passed: bool,
        fingerprint: str,
        rounds: int
    ) -> None:
        """
        Submit the Freivalds verification result on-chain.

        In production, this would create and sign a transaction on the blockchain.

        Args:
            task_id: Task identifier
            passed: Whether Freivalds verification passed
            fingerprint: Fingerprint hash of the matrices
            rounds: Number of rounds executed
        """
        await asyncio.sleep(0.2)  # Simulate blockchain transaction

        error_prob = self.compute_error_probability(rounds)

        logger.info(
            f"Submitted Freivalds result for task {task_id}: "
            f"passed={passed}, rounds={rounds}, error_prob={error_prob:.6f}"
        )

        # Update task status
        if task_id in self._pending_tasks:
            status = ValidationStatus.PASSED if passed else ValidationStatus.FAILED
            self._pending_tasks[task_id]['status'] = status.value

    def _hash_matrices(
        self,
        A: np.ndarray,
        B: np.ndarray,
        C: np.ndarray
    ) -> str:
        """
        Compute a hash fingerprint of the matrices.

        Used to verify that the exact same matrices are being validated.
        """
        import hashlib

        data = (
            A.tobytes() + B.tobytes() + C.tobytes()
        )
        return hashlib.sha256(data).hexdigest()[:16]

    def simulate_task_arrival(self, task_id: str) -> None:
        """
        Simulate a validation task arriving from the network.

        Used for demo purposes only.
        """
        self._pending_tasks[task_id] = {
            'task_id': task_id,
            'status': ValidationStatus.VALIDATING.value,
            'created_at': datetime.now()
        }
        logger.info(f"Simulated task arrival: {task_id}")


async def demo() -> None:
    """
    Demo showing a validator receiving a task, fetching inputs/results,
    running Freivalds verification, and submitting the result.
    """
    logger.info("=" * 70)
    logger.info("GAIA Protocol Validator Node Demo")
    logger.info("=" * 70)

    # Initialize validator
    validator = ValidatorNode(
        validator_id="validator-001",
        stake_address="0x1234567890abcdef1234567890abcdef12345678",
        rpc_endpoint="http://localhost:8545"
    )

    # Start validator
    await validator.start()

    # Simulate a task arriving
    task_id = "task-0001"
    validator.simulate_task_arrival(task_id)

    # Process the task
    logger.info("\nProcessing validation task...")
    await validator._process_validation_task(task_id)

    # Display results
    logger.info("\n" + "=" * 70)
    logger.info("Validation Results")
    logger.info("=" * 70)
    logger.info(f"Task ID: {task_id}")
    logger.info(f"Tasks Verified: {validator.stats.tasks_verified}")
    logger.info(f"Tasks Failed Freivalds: {validator.stats.tasks_failed_freivalds}")
    logger.info(f"Total Rewards Earned: {validator.stats.total_rewards_earned:.6f} GAIA")
    logger.info(f"Slash Events Detected: {validator.stats.slash_events_detected}")
    logger.info(f"Last Verification: {validator.stats.last_verification_timestamp}")

    # Stop validator
    await validator.stop()
    logger.info("\nValidator node stopped.")


if __name__ == "__main__":
    asyncio.run(demo())
