#!/usr/bin/env python3
"""
GAIA Protocol Miner Node
Decentralized GPU compute network for environmental science

Miners poll for matrix multiplication jobs (ML inference layers),
compute them using INT32-quantized arithmetic, commit to results before
revealing them (to prevent result-copying), and submit to on-chain TaskRegistry.
"""

import asyncio
import argparse
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple
from enum import Enum

import numpy as np
import aiohttp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('GaiaNode')


class JobType(Enum):
    """Supported job types in GAIA Protocol."""
    MATRIX_MULTIPLY = "matrix_multiply"
    CONV2D = "conv2d"
    LINEAR_LAYER = "linear_layer"


@dataclass
class NodeConfig:
    """Configuration for miner node."""
    miner_id: str
    stake_address: str
    rpc_endpoint: str
    private_key_path: str
    poll_interval: float = 5.0
    heartbeat_interval: float = 30.0
    job_timeout: float = 60.0
    min_stake: float = 10.0


@dataclass
class MinerStats:
    """Performance metrics for miner."""
    jobs_completed: int = 0
    jobs_failed: int = 0
    total_compute_time: float = 0.0
    total_rewards: float = 0.0
    avg_compute_time: float = 0.0
    last_job_time: Optional[datetime] = None

    def update_job_completion(self, compute_time: float, reward: float):
        """Update stats after job completion."""
        self.jobs_completed += 1
        self.total_compute_time += compute_time
        self.avg_compute_time = self.total_compute_time / self.jobs_completed
        self.total_rewards += reward
        self.last_job_time = datetime.now()

    def to_dict(self) -> Dict:
        """Convert stats to dictionary."""
        return {
            'jobs_completed': self.jobs_completed,
            'jobs_failed': self.jobs_failed,
            'total_compute_time': self.total_compute_time,
            'total_rewards': self.total_rewards,
            'avg_compute_time': self.avg_compute_time,
            'last_job_time': self.last_job_time.isoformat() if self.last_job_time else None,
        }


@dataclass
class JobResult:
    """Result of job computation."""
    task_id: str
    miner_id: str
    result_matrix: np.ndarray
    compute_time: float
    commitment: str
    fingerprint: str
    timestamp: int
    job_type: str


class MinerNode:
    """
    GAIA Protocol Miner Node.

    Handles job polling, computation, commitment, and on-chain submission.
    """

    def __init__(self, config: NodeConfig):
        """
        Initialize miner node.

        Args:
            config: NodeConfig with miner settings
        """
        self.config = config
        self.stats = MinerStats()
        self.running = False
        self.session: Optional[aiohttp.ClientSession] = None
        self.lock = asyncio.Lock()

        logger.info(f"MinerNode initialized: {config.miner_id}")

    async def start(self):
        """Begin listening for jobs."""
        if self.running:
            logger.warning("Node already running")
            return

        self.running = True
        self.session = aiohttp.ClientSession()

        logger.info(f"Starting MinerNode {self.config.miner_id}")
        logger.info(f"RPC Endpoint: {self.config.rpc_endpoint}")
        logger.info(f"Poll interval: {self.config.poll_interval}s")

        try:
            # Start polling and heartbeat tasks
            await asyncio.gather(
                self._poll_jobs_loop(),
                self._heartbeat_loop(),
            )
        except asyncio.CancelledError:
            logger.info("Node polling cancelled")
        except Exception as e:
            logger.error(f"Error in node operation: {e}")
        finally:
            await self.stop()

    async def stop(self):
        """Graceful shutdown."""
        self.running = False
        if self.session:
            await self.session.close()
        logger.info("MinerNode stopped")

    async def _poll_jobs_loop(self):
        """Main polling loop for new jobs."""
        while self.running:
            try:
                await self._poll_for_jobs()
                await asyncio.sleep(self.config.poll_interval)
            except Exception as e:
                logger.error(f"Error polling jobs: {e}")
                await asyncio.sleep(self.config.poll_interval)

    async def _poll_for_jobs(self):
        """Poll for pending jobs from TaskRegistry."""
        try:
            # Query TaskRegistry for PENDING tasks
            pending_tasks = await self._fetch_pending_tasks()

            if not pending_tasks:
                return

            logger.info(f"Found {len(pending_tasks)} pending tasks")

            for task in pending_tasks:
                if not self.running:
                    break

                # Verify job compliance
                if not self.verify_oracle_compliance(task.get('job_type')):
                    logger.warning(f"Job type {task.get('job_type')} not in scope")
                    continue

                # Compute job
                try:
                    result = await self.compute_job(task)
                    await self.submit_result(result.task_id, result)
                    self.stats.update_job_completion(result.compute_time, 0.1)
                except Exception as e:
                    logger.error(f"Failed to compute/submit job {task.get('id')}: {e}")
                    self.stats.jobs_failed += 1

        except Exception as e:
            logger.error(f"Error in job polling: {e}")

    async def _fetch_pending_tasks(self) -> list:
        """Fetch pending tasks from on-chain TaskRegistry."""
        if not self.session:
            return []

        try:
            # JSON-RPC call to get pending tasks
            payload = {
                "jsonrpc": "2.0",
                "method": "taskRegistry_getPendingTasks",
                "params": [self.config.miner_id, 10],  # max 10 tasks
                "id": 1,
            }

            async with self.session.post(
                self.config.rpc_endpoint,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('result', [])
        except asyncio.TimeoutError:
            logger.warning("Task fetch timeout")
        except Exception as e:
            logger.debug(f"Task fetch error: {e}")

        return []

    async def compute_job(self, job_spec: Dict) -> JobResult:
        """
        Execute a matrix multiplication job.

        Args:
            job_spec: Job specification with matrices and parameters

        Returns:
            JobResult with computation output
        """
        start_time = time.time()
        task_id = job_spec.get('id', 'unknown')
        job_type = job_spec.get('job_type', 'matrix_multiply')

        logger.info(f"Computing job {task_id} ({job_type})")

        try:
            # Parse input matrices
            matrix_a = np.array(job_spec.get('matrix_a', []), dtype=np.float32)
            matrix_b = np.array(job_spec.get('matrix_b', []), dtype=np.float32)

            # Quantize to INT32 for deterministic computation
            matrix_a_q = self.quantize_matrix(matrix_a)
            matrix_b_q = self.quantize_matrix(matrix_b)

            # Perform computation
            if job_type == 'matrix_multiply' or job_type == JobType.MATRIX_MULTIPLY.value:
                result = np.matmul(matrix_a_q, matrix_b_q)
            else:
                # Default to matrix multiply
                result = np.matmul(matrix_a_q, matrix_b_q)

            # Generate commitment and fingerprint
            timestamp = int(time.time())
            commitment = self.generate_commitment(task_id, result, timestamp)
            fingerprint = self.generate_result_fingerprint(task_id, result)

            compute_time = time.time() - start_time

            logger.info(f"Job {task_id} computed in {compute_time:.4f}s")

            return JobResult(
                task_id=task_id,
                miner_id=self.config.miner_id,
                result_matrix=result,
                compute_time=compute_time,
                commitment=commitment,
                fingerprint=fingerprint,
                timestamp=timestamp,
                job_type=job_type,
            )

        except Exception as e:
            logger.error(f"Computation error for job {task_id}: {e}")
            raise

    async def submit_result(self, task_id: str, result: JobResult):
        """
        Submit job result to on-chain TaskRegistry.

        Two-phase commit:
        1. Submit commitment hash (prevents result copying)
        2. Reveal result and fingerprint for verification

        Args:
            task_id: Task identifier
            result: JobResult object
        """
        if not self.session:
            logger.warning("No session for result submission")
            return

        try:
            # Phase 1: Commit to result
            commit_payload = {
                "jsonrpc": "2.0",
                "method": "taskRegistry_commitResult",
                "params": [
                    task_id,
                    self.config.miner_id,
                    result.commitment,
                ],
                "id": 1,
            }

            async with self.session.post(
                self.config.rpc_endpoint,
                json=commit_payload,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as response:
                if response.status != 200:
                    logger.error(f"Commitment failed: {response.status}")
                    return

            # Small delay before revealing
            await asyncio.sleep(0.1)

            # Phase 2: Reveal result
            reveal_payload = {
                "jsonrpc": "2.0",
                "method": "taskRegistry_revealResult",
                "params": [
                    task_id,
                    self.config.miner_id,
                    result.result_matrix.tolist(),
                    result.fingerprint,
                    result.timestamp,
                ],
                "id": 2,
            }

            async with self.session.post(
                self.config.rpc_endpoint,
                json=reveal_payload,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as response:
                if response.status == 200:
                    logger.info(f"Result submitted for task {task_id}")
                else:
                    logger.error(f"Result submission failed: {response.status}")

        except Exception as e:
            logger.error(f"Result submission error for {task_id}: {e}")

    def generate_commitment(self, job_id: str, result_matrix: np.ndarray,
                          timestamp: int) -> str:
        """
        Generate SHA-256 commitment hash.

        Prevents miners from copying results from others before revealing.

        Args:
            job_id: Job identifier
            result_matrix: Computed result matrix
            timestamp: Computation timestamp

        Returns:
            Hex-encoded SHA-256 commitment hash
        """
        result_bytes = result_matrix.astype(np.int32).tobytes()

        commitment_data = (
            b"GAIA_COMMITMENT_V1" +
            job_id.encode() +
            self.config.miner_id.encode() +
            str(timestamp).encode() +
            result_bytes
        )

        commitment = hashlib.sha256(commitment_data).hexdigest()
        logger.debug(f"Generated commitment: {commitment[:16]}...")

        return commitment

    def generate_result_fingerprint(self, job_id: str,
                                    result_matrix: np.ndarray) -> str:
        """
        Generate result fingerprint for consensus verification.

        Used to verify miner agreement on correct computation.

        Args:
            job_id: Job identifier
            result_matrix: Result matrix

        Returns:
            Hex-encoded SHA-256 fingerprint
        """
        result_bytes = result_matrix.astype(np.int32).tobytes()

        fingerprint_data = (
            b"GAIA_RESULT_FINGERPRINT_V1" +
            job_id.encode() +
            result_bytes
        )

        fingerprint = hashlib.sha256(fingerprint_data).hexdigest()
        logger.debug(f"Generated fingerprint: {fingerprint[:16]}...")

        return fingerprint

    def quantize_matrix(self, matrix: np.ndarray) -> np.ndarray:
        """
        Quantize matrix to INT32 for deterministic computation.

        Ensures all miners produce identical results.

        Args:
            matrix: Input matrix as float

        Returns:
            Quantized INT32 matrix
        """
        # Try to use freivalds module if available
        try:
            from freivalds import quantize_to_int32
            return quantize_to_int32(matrix)
        except ImportError:
            pass

        # Fallback: simple quantization scheme
        # Scale to [-2^31, 2^31) range
        scale_factor = 10000.0
        matrix_scaled = np.clip(
            matrix * scale_factor,
            -2**31,
            2**31 - 1
        )

        return matrix_scaled.astype(np.int32)

    def verify_oracle_compliance(self, job_type: Optional[str]) -> bool:
        """
        Verify job type is in-scope for GAIA Protocol.

        Args:
            job_type: Job type string

        Returns:
            True if job type is supported
        """
        supported_types = {
            JobType.MATRIX_MULTIPLY.value,
            JobType.CONV2D.value,
            JobType.LINEAR_LAYER.value,
        }

        if job_type in supported_types:
            return True

        # Default allow matrix_multiply
        return job_type in ['matrix_multiply', None]

    async def _heartbeat_loop(self):
        """Periodically broadcast node availability."""
        while self.running:
            try:
                await self.heartbeat()
                await asyncio.sleep(self.config.heartbeat_interval)
            except Exception as e:
                logger.debug(f"Heartbeat error: {e}")
                await asyncio.sleep(self.config.heartbeat_interval)

    async def heartbeat(self):
        """Send heartbeat to indicate node availability."""
        if not self.session:
            return

        try:
            stats_dict = self.stats.to_dict()

            payload = {
                "jsonrpc": "2.0",
                "method": "nodeRegistry_heartbeat",
                "params": [
                    self.config.miner_id,
                    self.config.stake_address,
                    stats_dict,
                ],
                "id": 1,
            }

            async with self.session.post(
                self.config.rpc_endpoint,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=3),
            ) as response:
                if response.status == 200:
                    logger.debug(f"Heartbeat sent: {self.stats.jobs_completed} jobs")

        except Exception as e:
            logger.debug(f"Heartbeat transmission error: {e}")

    def get_status(self) -> Dict:
        """Get current node status."""
        return {
            'miner_id': self.config.miner_id,
            'running': self.running,
            'stats': self.stats.to_dict(),
        }


async def run_miner(config: NodeConfig):
    """
    Run miner node.

    Args:
        config: NodeConfig with settings
    """
    node = MinerNode(config)

    try:
        await node.start()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    finally:
        await node.stop()


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='GAIA Protocol Miner Node'
    )
    parser.add_argument('--miner-id', required=True, help='Miner identifier')
    parser.add_argument('--stake-address', required=True, help='Stake wallet address')
    parser.add_argument('--rpc-endpoint', default='http://localhost:8545',
                       help='Blockchain RPC endpoint')
    parser.add_argument('--private-key-path', default='~/.gaia/key.pem',
                       help='Path to private key')
    parser.add_argument('--poll-interval', type=float, default=5.0,
                       help='Job poll interval (seconds)')
    parser.add_argument('--demo', action='store_true',
                       help='Run in demo mode without blockchain')

    args = parser.parse_args()

    if args.demo:
        asyncio.run(demo_mode())
    else:
        config = NodeConfig(
            miner_id=args.miner_id,
            stake_address=args.stake_address,
            rpc_endpoint=args.rpc_endpoint,
            private_key_path=args.private_key_path,
            poll_interval=args.poll_interval,
        )
        asyncio.run(run_miner(config))


async def demo_mode():
    """
    DEMO MODE: Run miner without blockchain connection.

    Shows the complete workflow:
    1. Receive job
    2. Compute result
    3. Generate commitment
    4. Submit result
    """
    logger.info("=" * 60)
    logger.info("GAIA Protocol Miner - DEMO MODE")
    logger.info("=" * 60)

    # Create demo config
    config = NodeConfig(
        miner_id="demo-miner-001",
        stake_address="0xDEMO1234567890",
        rpc_endpoint="http://localhost:8545",
        private_key_path="~/.gaia/demo.key",
    )

    node = MinerNode(config)

    # Create demo job
    demo_job = {
        'id': 'task-demo-001',
        'job_type': 'matrix_multiply',
        'matrix_a': [[1.0, 2.0], [3.0, 4.0]],
        'matrix_b': [[5.0, 6.0], [7.0, 8.0]],
    }

    logger.info("\n[1] Job Received")
    logger.info(f"Task ID: {demo_job['id']}")
    logger.info(f"Job Type: {demo_job['job_type']}")
    logger.info(f"Matrix A: {demo_job['matrix_a']}")
    logger.info(f"Matrix B: {demo_job['matrix_b']}")

    # Compute job
    logger.info("\n[2] Computing Job...")
    result = await node.compute_job(demo_job)
    logger.info(f"Result shape: {result.result_matrix.shape}")
    logger.info(f"Result matrix:\n{result.result_matrix}")
    logger.info(f"Compute time: {result.compute_time:.4f}s")

    # Show commitment
    logger.info("\n[3] Commitment Generated (Phase 1)")
    logger.info(f"Commitment: {result.commitment}")
    logger.info(f"Timestamp: {result.timestamp}")

    # Show fingerprint
    logger.info("\n[4] Result Fingerprint (Consensus)")
    logger.info(f"Fingerprint: {result.fingerprint}")

    # Show stats
    logger.info("\n[5] Miner Statistics")
    logger.info(f"Jobs completed: {node.stats.jobs_completed}")
    logger.info(f"Avg compute time: {node.stats.avg_compute_time:.4f}s")
    logger.info(f"Total rewards: {node.stats.total_rewards}")

    logger.info("\n[6] Would submit to chain:")
    logger.info(f"Method 1: taskRegistry_commitResult({demo_job['id']}, ...)")
    logger.info(f"Method 2: taskRegistry_revealResult({demo_job['id']}, ...)")

    logger.info("\n" + "=" * 60)
    logger.info("DEMO MODE COMPLETE")
    logger.info("=" * 60)


if __name__ == '__main__':
    main()
