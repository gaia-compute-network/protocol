"""
Comprehensive pytest tests for GAIA FastAPI Server
====================================================

Tests all 9 API endpoints with happy path and error cases using:
- pytest + httpx AsyncClient
- ASGITransport for direct ASGI app testing
- Parametrized test cases for coverage

Endpoints tested:
1. POST /v1/jobs/submit
2. GET /v1/jobs/{job_id}
3. GET /v1/jobs/{job_id}/result
4. POST /v1/miners/register
5. GET /v1/miners/{miner_id}/stats
6. GET /v1/network/stats
7. GET /v1/network/oracle
8. GET /v1/csrd/report/{job_id}
9. GET /health
"""

import pytest
import httpx
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "node"))

from api_server import (
    app,
    JobStatus,
    MinerStatus,
    GPUType,
    job_store,
    miner_store,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(autouse=True)
def clear_stores():
    """Clear in-memory stores before each test."""
    job_store.clear()
    miner_store.clear()
    yield
    job_store.clear()
    miner_store.clear()


@pytest.fixture
async def client():
    """Create AsyncClient for testing."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def valid_api_key():
    """Valid API key for testing."""
    return "test-api-key-12345"


@pytest.fixture
def job_submit_payload():
    """Valid job submission payload."""
    return {
        "job_type": "matrix_multiply",
        "input_hash": "QmX7c85f0d3e1a2b9f4c6e8d1a3b5c7e9f1a3b5c7e9f1a3b5c",
        "metadata_country": "US",
        "reward_gaia": 100.0,
        "requester_address": "0x1234567890abcdef1234567890abcdef12345678",
    }


@pytest.fixture
def miner_register_payload():
    """Valid miner registration payload."""
    return {
        "miner_id": "miner-001",
        "stake_address": "0xabcdef1234567890abcdef1234567890abcdef12",
        "node_url": "http://miner.local:8080",
        "gpu_type": "nvidia_h100",
        "location_country": "US",
    }


# ============================================================================
# Test Group 1: POST /v1/jobs/submit
# ============================================================================

class TestJobSubmit:
    """Test job submission endpoint."""

    @pytest.mark.asyncio
    async def test_submit_job_valid(self, client, valid_api_key, job_submit_payload):
        """Happy path: submit a valid job."""
        response = await client.post(
            "/v1/jobs/submit",
            json=job_submit_payload,
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 201
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "submitted"
        assert data["estimated_completion_seconds"] == 180
        assert data["job_id"].startswith("job-")

    @pytest.mark.asyncio
    async def test_submit_job_missing_api_key(self, client, job_submit_payload):
        """Error: missing API key header."""
        response = await client.post(
            "/v1/jobs/submit",
            json=job_submit_payload,
        )
        assert response.status_code == 401
        assert "API key" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_submit_job_missing_field_job_type(self, client, valid_api_key, job_submit_payload):
        """Error: missing required field 'job_type'."""
        del job_submit_payload["job_type"]
        response = await client.post(
            "/v1/jobs/submit",
            json=job_submit_payload,
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_submit_job_missing_field_input_hash(self, client, valid_api_key, job_submit_payload):
        """Error: missing required field 'input_hash'."""
        del job_submit_payload["input_hash"]
        response = await client.post(
            "/v1/jobs/submit",
            json=job_submit_payload,
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_submit_job_missing_field_metadata_country(self, client, valid_api_key, job_submit_payload):
        """Error: missing required field 'metadata_country'."""
        del job_submit_payload["metadata_country"]
        response = await client.post(
            "/v1/jobs/submit",
            json=job_submit_payload,
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_submit_job_missing_field_reward(self, client, valid_api_key, job_submit_payload):
        """Error: missing required field 'reward_gaia'."""
        del job_submit_payload["reward_gaia"]
        response = await client.post(
            "/v1/jobs/submit",
            json=job_submit_payload,
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_submit_job_missing_field_requester(self, client, valid_api_key, job_submit_payload):
        """Error: missing required field 'requester_address'."""
        del job_submit_payload["requester_address"]
        response = await client.post(
            "/v1/jobs/submit",
            json=job_submit_payload,
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_submit_job_invalid_reward_negative(self, client, valid_api_key, job_submit_payload):
        """Error: negative reward amount."""
        job_submit_payload["reward_gaia"] = -100.0
        response = await client.post(
            "/v1/jobs/submit",
            json=job_submit_payload,
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_submit_job_invalid_reward_zero(self, client, valid_api_key, job_submit_payload):
        """Error: zero reward amount."""
        job_submit_payload["reward_gaia"] = 0.0
        response = await client.post(
            "/v1/jobs/submit",
            json=job_submit_payload,
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_submit_job_with_custom_job_type(self, client, valid_api_key, job_submit_payload):
        """Happy path: submit with custom job_type (not just matrix_multiply)."""
        job_submit_payload["job_type"] = "inference"
        response = await client.post(
            "/v1/jobs/submit",
            json=job_submit_payload,
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "submitted"

    @pytest.mark.asyncio
    async def test_submit_job_stores_in_job_store(self, client, valid_api_key, job_submit_payload):
        """Verify job is stored in global job_store."""
        response = await client.post(
            "/v1/jobs/submit",
            json=job_submit_payload,
            headers={"X-API-Key": valid_api_key},
        )
        job_id = response.json()["job_id"]
        assert job_id in job_store
        assert job_store[job_id].job_type == "matrix_multiply"


# ============================================================================
# Test Group 2: GET /v1/jobs/{job_id}
# ============================================================================

class TestGetJobDetails:
    """Test get job details endpoint."""

    @pytest.mark.asyncio
    async def test_get_job_existing(self, client, valid_api_key, job_submit_payload):
        """Happy path: retrieve existing job details."""
        # First submit a job
        submit_response = await client.post(
            "/v1/jobs/submit",
            json=job_submit_payload,
            headers={"X-API-Key": valid_api_key},
        )
        job_id = submit_response.json()["job_id"]

        # Then fetch it
        response = await client.get(
            f"/v1/jobs/{job_id}",
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert data["status"] == "submitted"
        assert data["job_type"] == "matrix_multiply"
        assert data["requester_address"] == job_submit_payload["requester_address"]
        assert data["reward_gaia"] == job_submit_payload["reward_gaia"]
        assert data["input_hash"] == job_submit_payload["input_hash"]
        assert data["metadata_country"] == job_submit_payload["metadata_country"]

    @pytest.mark.asyncio
    async def test_get_job_unknown_id(self, client, valid_api_key):
        """Error: job ID not found."""
        response = await client.get(
            "/v1/jobs/job-unknown-999",
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_job_missing_api_key(self, client, job_submit_payload):
        """Error: missing API key."""
        submit_response = await client.post(
            "/v1/jobs/submit",
            json=job_submit_payload,
            headers={"X-API-Key": "test-key"},
        )
        job_id = submit_response.json()["job_id"]

        response = await client.get(f"/v1/jobs/{job_id}")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_job_includes_timestamps(self, client, valid_api_key, job_submit_payload):
        """Verify response includes created_at and updated_at."""
        submit_response = await client.post(
            "/v1/jobs/submit",
            json=job_submit_payload,
            headers={"X-API-Key": valid_api_key},
        )
        job_id = submit_response.json()["job_id"]

        response = await client.get(
            f"/v1/jobs/{job_id}",
            headers={"X-API-Key": valid_api_key},
        )
        data = response.json()
        assert "created_at" in data
        assert "updated_at" in data
        # Verify ISO format
        datetime.fromisoformat(data["created_at"])
        datetime.fromisoformat(data["updated_at"])

    @pytest.mark.asyncio
    async def test_get_job_miner_list(self, client, valid_api_key, job_submit_payload):
        """Verify miner_ids list is present."""
        submit_response = await client.post(
            "/v1/jobs/submit",
            json=job_submit_payload,
            headers={"X-API-Key": valid_api_key},
        )
        job_id = submit_response.json()["job_id"]

        response = await client.get(
            f"/v1/jobs/{job_id}",
            headers={"X-API-Key": valid_api_key},
        )
        data = response.json()
        assert "miner_ids" in data
        assert isinstance(data["miner_ids"], list)


# ============================================================================
# Test Group 3: GET /v1/jobs/{job_id}/result
# ============================================================================

class TestGetJobResult:
    """Test get job result endpoint."""

    @pytest.mark.asyncio
    async def test_get_job_result_verified(self, client, valid_api_key, job_submit_payload):
        """Happy path: get result of a verified job."""
        # Submit job
        submit_response = await client.post(
            "/v1/jobs/submit",
            json=job_submit_payload,
            headers={"X-API-Key": valid_api_key},
        )
        job_id = submit_response.json()["job_id"]

        # Manually mark job as verified
        job_store[job_id].status = JobStatus.VERIFIED
        job_store[job_id].result_fingerprint = "fp-abc123xyz"
        job_store[job_id].freivalds_passed = True
        job_store[job_id].error_probability = 2.0 ** (-10)
        job_store[job_id].on_chain_hash = "0xdeadbeef"

        # Fetch result
        response = await client.get(
            f"/v1/jobs/{job_id}/result",
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert data["verified"] is True
        assert data["result_fingerprint"] == "fp-abc123xyz"
        assert data["freivalds_passed"] is True
        assert data["error_probability"] == 2.0 ** (-10)
        assert data["on_chain_hash"] == "0xdeadbeef"

    @pytest.mark.asyncio
    async def test_get_job_result_pending(self, client, valid_api_key, job_submit_payload):
        """Error: job not yet verified."""
        submit_response = await client.post(
            "/v1/jobs/submit",
            json=job_submit_payload,
            headers={"X-API-Key": valid_api_key},
        )
        job_id = submit_response.json()["job_id"]

        # Try to get result of pending job
        response = await client.get(
            f"/v1/jobs/{job_id}/result",
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 202
        assert "not yet verified" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_job_result_unknown_job(self, client, valid_api_key):
        """Error: job ID not found."""
        response = await client.get(
            "/v1/jobs/job-unknown-999/result",
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_job_result_missing_api_key(self, client, job_submit_payload):
        """Error: missing API key."""
        submit_response = await client.post(
            "/v1/jobs/submit",
            json=job_submit_payload,
            headers={"X-API-Key": "test-key"},
        )
        job_id = submit_response.json()["job_id"]

        response = await client.get(f"/v1/jobs/{job_id}/result")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_job_result_csrd_report_url(self, client, valid_api_key, job_submit_payload):
        """Verify CSRD report URL is included for verified jobs."""
        submit_response = await client.post(
            "/v1/jobs/submit",
            json=job_submit_payload,
            headers={"X-API-Key": valid_api_key},
        )
        job_id = submit_response.json()["job_id"]

        job_store[job_id].status = JobStatus.VERIFIED
        job_store[job_id].result_fingerprint = "fp-test"

        response = await client.get(
            f"/v1/jobs/{job_id}/result",
            headers={"X-API-Key": valid_api_key},
        )
        data = response.json()
        assert "csrd_report_url" in data
        assert data["csrd_report_url"] == f"/v1/csrd/report/{job_id}"


# ============================================================================
# Test Group 4: POST /v1/miners/register
# ============================================================================

class TestMinerRegister:
    """Test miner registration endpoint."""

    @pytest.mark.asyncio
    async def test_register_miner_valid(self, client, valid_api_key, miner_register_payload):
        """Happy path: register a new miner."""
        response = await client.post(
            "/v1/miners/register",
            json=miner_register_payload,
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["registered"] is True
        assert data["miner_id"] == "miner-001"
        assert data["first_job_available_in_seconds"] == 10

    @pytest.mark.asyncio
    async def test_register_miner_duplicate(self, client, valid_api_key, miner_register_payload):
        """Error: duplicate miner ID."""
        # Register first time
        await client.post(
            "/v1/miners/register",
            json=miner_register_payload,
            headers={"X-API-Key": valid_api_key},
        )

        # Try to register again with same ID
        response = await client.post(
            "/v1/miners/register",
            json=miner_register_payload,
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 409
        assert "already registered" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_register_miner_missing_api_key(self, client, miner_register_payload):
        """Error: missing API key."""
        response = await client.post(
            "/v1/miners/register",
            json=miner_register_payload,
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_register_miner_missing_field_miner_id(self, client, valid_api_key, miner_register_payload):
        """Error: missing miner_id field."""
        del miner_register_payload["miner_id"]
        response = await client.post(
            "/v1/miners/register",
            json=miner_register_payload,
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_miner_missing_field_stake_address(self, client, valid_api_key, miner_register_payload):
        """Error: missing stake_address field."""
        del miner_register_payload["stake_address"]
        response = await client.post(
            "/v1/miners/register",
            json=miner_register_payload,
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_miner_missing_field_node_url(self, client, valid_api_key, miner_register_payload):
        """Error: missing node_url field."""
        del miner_register_payload["node_url"]
        response = await client.post(
            "/v1/miners/register",
            json=miner_register_payload,
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_miner_missing_field_gpu_type(self, client, valid_api_key, miner_register_payload):
        """Error: missing gpu_type field."""
        del miner_register_payload["gpu_type"]
        response = await client.post(
            "/v1/miners/register",
            json=miner_register_payload,
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_miner_missing_field_location(self, client, valid_api_key, miner_register_payload):
        """Error: missing location_country field."""
        del miner_register_payload["location_country"]
        response = await client.post(
            "/v1/miners/register",
            json=miner_register_payload,
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_miner_invalid_gpu_type(self, client, valid_api_key, miner_register_payload):
        """Error: invalid GPU type."""
        miner_register_payload["gpu_type"] = "invalid_gpu"
        response = await client.post(
            "/v1/miners/register",
            json=miner_register_payload,
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_miner_stores_in_miner_store(self, client, valid_api_key, miner_register_payload):
        """Verify miner is stored in global miner_store."""
        await client.post(
            "/v1/miners/register",
            json=miner_register_payload,
            headers={"X-API-Key": valid_api_key},
        )
        assert "miner-001" in miner_store
        assert miner_store["miner-001"].gpu_type == GPUType.NVIDIA_H100

    @pytest.mark.asyncio
    async def test_register_miner_with_different_gpu_types(self, client, valid_api_key, miner_register_payload):
        """Happy path: register miners with different GPU types."""
        gpu_types = ["nvidia_a100", "nvidia_a6000", "amd_mi300"]
        for i, gpu in enumerate(gpu_types):
            payload = miner_register_payload.copy()
            payload["miner_id"] = f"miner-{i:03d}"
            payload["gpu_type"] = gpu
            response = await client.post(
                "/v1/miners/register",
                json=payload,
                headers={"X-API-Key": valid_api_key},
            )
            assert response.status_code == 201


# ============================================================================
# Test Group 5: GET /v1/miners/{miner_id}/stats
# ============================================================================

class TestGetMinerStats:
    """Test get miner stats endpoint."""

    @pytest.mark.asyncio
    async def test_get_miner_stats_existing(self, client, valid_api_key, miner_register_payload):
        """Happy path: get stats of registered miner."""
        # Register miner
        await client.post(
            "/v1/miners/register",
            json=miner_register_payload,
            headers={"X-API-Key": valid_api_key},
        )

        # Get stats
        response = await client.get(
            "/v1/miners/miner-001/stats",
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["miner_id"] == "miner-001"
        assert data["status"] == "online"
        assert data["gpu_type"] == "nvidia_h100"
        assert data["jobs_completed"] == 0
        assert data["jobs_failed"] == 0
        assert data["avg_job_time_seconds"] == 0.0
        assert data["total_earnings_gaia"] == 0.0
        assert data["stake_amount_gaia"] == 100.0

    @pytest.mark.asyncio
    async def test_get_miner_stats_unknown_id(self, client, valid_api_key):
        """Error: miner ID not found."""
        response = await client.get(
            "/v1/miners/miner-unknown-999/stats",
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_miner_stats_missing_api_key(self, client, miner_register_payload):
        """Error: missing API key."""
        await client.post(
            "/v1/miners/register",
            json=miner_register_payload,
            headers={"X-API-Key": "test-key"},
        )
        response = await client.get("/v1/miners/miner-001/stats")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_miner_stats_includes_timestamps(self, client, valid_api_key, miner_register_payload):
        """Verify response includes last_heartbeat timestamp."""
        await client.post(
            "/v1/miners/register",
            json=miner_register_payload,
            headers={"X-API-Key": valid_api_key},
        )
        response = await client.get(
            "/v1/miners/miner-001/stats",
            headers={"X-API-Key": valid_api_key},
        )
        data = response.json()
        assert "last_heartbeat" in data
        # Verify ISO format
        datetime.fromisoformat(data["last_heartbeat"])

    @pytest.mark.asyncio
    async def test_get_miner_stats_with_jobs(self, client, valid_api_key, miner_register_payload):
        """Verify stats calculation with completed jobs."""
        await client.post(
            "/v1/miners/register",
            json=miner_register_payload,
            headers={"X-API-Key": valid_api_key},
        )

        # Manually update miner stats
        miner = miner_store["miner-001"]
        miner.jobs_completed = 5
        miner.jobs_failed = 1
        miner.total_job_time = 500.0
        miner.total_earnings_gaia = 250.0

        response = await client.get(
            "/v1/miners/miner-001/stats",
            headers={"X-API-Key": valid_api_key},
        )
        data = response.json()
        assert data["jobs_completed"] == 5
        assert data["jobs_failed"] == 1
        assert data["avg_job_time_seconds"] == 100.0  # 500 / 5
        assert data["total_earnings_gaia"] == 250.0


# ============================================================================
# Test Group 6: GET /v1/network/stats
# ============================================================================

class TestGetNetworkStats:
    """Test get network stats endpoint."""

    @pytest.mark.asyncio
    async def test_get_network_stats_empty(self, client, valid_api_key):
        """Happy path: get stats with empty network."""
        response = await client.get(
            "/v1/network/stats",
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_jobs"] == 0
        assert data["verified_jobs"] == 0
        assert data["active_miners"] == 0
        assert data["total_tokens_burned"] == 0.0
        assert data["burn_rate_24h"] == 0.0

    @pytest.mark.asyncio
    async def test_get_network_stats_with_jobs_and_miners(
        self, client, valid_api_key, job_submit_payload, miner_register_payload
    ):
        """Happy path: get stats with jobs and miners."""
        # Register 2 miners
        for i in range(2):
            payload = miner_register_payload.copy()
            payload["miner_id"] = f"miner-{i:03d}"
            await client.post(
                "/v1/miners/register",
                json=payload,
                headers={"X-API-Key": valid_api_key},
            )

        # Submit 3 jobs
        for i in range(3):
            payload = job_submit_payload.copy()
            payload["reward_gaia"] = 100.0 + i * 10
            await client.post(
                "/v1/jobs/submit",
                json=payload,
                headers={"X-API-Key": valid_api_key},
            )

        # Mark one job as verified
        job_id = list(job_store.keys())[0]
        job_store[job_id].status = JobStatus.VERIFIED

        response = await client.get(
            "/v1/network/stats",
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_jobs"] == 3
        assert data["verified_jobs"] == 1
        assert data["active_miners"] == 2
        assert data["total_tokens_burned"] > 0.0

    @pytest.mark.asyncio
    async def test_get_network_stats_missing_api_key(self, client):
        """Error: missing API key."""
        response = await client.get("/v1/network/stats")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_network_stats_includes_timestamp(self, client, valid_api_key):
        """Verify response includes network_timestamp."""
        response = await client.get(
            "/v1/network/stats",
            headers={"X-API-Key": valid_api_key},
        )
        data = response.json()
        assert "network_timestamp" in data
        # Verify ISO format
        datetime.fromisoformat(data["network_timestamp"])


# ============================================================================
# Test Group 7: GET /v1/network/oracle
# ============================================================================

class TestGetOracle:
    """Test get oracle endpoint."""

    @pytest.mark.asyncio
    async def test_get_oracle_valid(self, client, valid_api_key):
        """Happy path: get oracle configuration."""
        response = await client.get(
            "/v1/network/oracle",
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 200
        data = response.json()
        assert "model_hash" in data
        assert "model_cid" in data
        assert "job_types_in_scope" in data
        assert "next_update_window_years" in data
        assert "last_update" in data
        assert isinstance(data["job_types_in_scope"], list)
        assert len(data["job_types_in_scope"]) > 0

    @pytest.mark.asyncio
    async def test_get_oracle_job_types(self, client, valid_api_key):
        """Verify oracle returns expected job types."""
        response = await client.get(
            "/v1/network/oracle",
            headers={"X-API-Key": valid_api_key},
        )
        data = response.json()
        expected_types = {
            "matrix_multiply",
            "inference",
            "hash_verification",
            "cryptographic_proof",
        }
        assert set(data["job_types_in_scope"]) == expected_types

    @pytest.mark.asyncio
    async def test_get_oracle_missing_api_key(self, client):
        """Error: missing API key."""
        response = await client.get("/v1/network/oracle")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_oracle_model_fields(self, client, valid_api_key):
        """Verify oracle includes model hash and CID."""
        response = await client.get(
            "/v1/network/oracle",
            headers={"X-API-Key": valid_api_key},
        )
        data = response.json()
        assert data["model_hash"].startswith("sha256:")
        assert data["model_cid"].startswith("Qm")

    @pytest.mark.asyncio
    async def test_get_oracle_timestamp(self, client, valid_api_key):
        """Verify oracle includes last_update timestamp."""
        response = await client.get(
            "/v1/network/oracle",
            headers={"X-API-Key": valid_api_key},
        )
        data = response.json()
        # Verify ISO format
        datetime.fromisoformat(data["last_update"])


# ============================================================================
# Test Group 8: GET /v1/csrd/report/{job_id}
# ============================================================================

class TestGetCSRDReport:
    """Test CSRD compliance report endpoint."""

    @pytest.mark.asyncio
    async def test_get_csrd_report_verified_job(self, client, valid_api_key, job_submit_payload):
        """Happy path: get CSRD report for verified job."""
        # Submit and verify job
        submit_response = await client.post(
            "/v1/jobs/submit",
            json=job_submit_payload,
            headers={"X-API-Key": valid_api_key},
        )
        job_id = submit_response.json()["job_id"]

        job_store[job_id].status = JobStatus.VERIFIED
        job_store[job_id].result_fingerprint = "fp-test"

        # Get CSRD report
        response = await client.get(
            f"/v1/csrd/report/{job_id}",
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert "esrs_e4_data" in data
        assert "verification_timestamp" in data
        assert "verification_hash" in data
        assert data["compliance_status"] == "compliant"

    @pytest.mark.asyncio
    async def test_get_csrd_report_pending_job(self, client, valid_api_key, job_submit_payload):
        """Error: job not yet verified."""
        submit_response = await client.post(
            "/v1/jobs/submit",
            json=job_submit_payload,
            headers={"X-API-Key": valid_api_key},
        )
        job_id = submit_response.json()["job_id"]

        response = await client.get(
            f"/v1/csrd/report/{job_id}",
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 202
        assert "not yet verified" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_csrd_report_unknown_job(self, client, valid_api_key):
        """Error: job ID not found."""
        response = await client.get(
            "/v1/csrd/report/job-unknown-999",
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_csrd_report_missing_api_key(self, client, job_submit_payload):
        """Error: missing API key."""
        submit_response = await client.post(
            "/v1/jobs/submit",
            json=job_submit_payload,
            headers={"X-API-Key": "test-key"},
        )
        job_id = submit_response.json()["job_id"]
        job_store[job_id].status = JobStatus.VERIFIED
        job_store[job_id].result_fingerprint = "fp-test"

        response = await client.get(f"/v1/csrd/report/{job_id}")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_csrd_report_esrs_e4_data(self, client, valid_api_key, job_submit_payload):
        """Verify CSRD report includes ESRS E4 compliance data."""
        submit_response = await client.post(
            "/v1/jobs/submit",
            json=job_submit_payload,
            headers={"X-API-Key": valid_api_key},
        )
        job_id = submit_response.json()["job_id"]

        job_store[job_id].status = JobStatus.VERIFIED
        job_store[job_id].result_fingerprint = "fp-test"

        response = await client.get(
            f"/v1/csrd/report/{job_id}",
            headers={"X-API-Key": valid_api_key},
        )
        data = response.json()
        esrs = data["esrs_e4_data"]

        # Verify ESRS E4 compliance fields
        assert "esrs_e4_compliance" in esrs
        assert "data_governance" in esrs["esrs_e4_compliance"]
        assert "computation_verification" in esrs["esrs_e4_compliance"]
        assert "result_integrity" in esrs["esrs_e4_compliance"]


# ============================================================================
# Test Group 9: GET /health
# ============================================================================

class TestHealthCheck:
    """Test health check endpoint."""

    @pytest.mark.asyncio
    async def test_health_check(self, client):
        """Happy path: get health status (no API key required)."""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == "1.0.0"
        assert "uptime_seconds" in data
        assert data["uptime_seconds"] >= 0

    @pytest.mark.asyncio
    async def test_health_check_no_api_key_required(self, client):
        """Verify health endpoint doesn't require API key."""
        response = await client.get("/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_check_uptime(self, client):
        """Verify uptime is positive."""
        response = await client.get("/health")
        data = response.json()
        assert data["uptime_seconds"] >= 0


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests combining multiple endpoints."""

    @pytest.mark.asyncio
    async def test_full_job_workflow(
        self, client, valid_api_key, job_submit_payload, miner_register_payload
    ):
        """Test full workflow: register miner -> submit job -> get details -> get result."""
        # Register miner
        miner_response = await client.post(
            "/v1/miners/register",
            json=miner_register_payload,
            headers={"X-API-Key": valid_api_key},
        )
        assert miner_response.status_code == 201

        # Submit job
        job_response = await client.post(
            "/v1/jobs/submit",
            json=job_submit_payload,
            headers={"X-API-Key": valid_api_key},
        )
        assert job_response.status_code == 201
        job_id = job_response.json()["job_id"]

        # Get job details
        details_response = await client.get(
            f"/v1/jobs/{job_id}",
            headers={"X-API-Key": valid_api_key},
        )
        assert details_response.status_code == 200

        # Verify job, then get result
        job_store[job_id].status = JobStatus.VERIFIED
        job_store[job_id].result_fingerprint = "fp-verified"

        result_response = await client.get(
            f"/v1/jobs/{job_id}/result",
            headers={"X-API-Key": valid_api_key},
        )
        assert result_response.status_code == 200

    @pytest.mark.asyncio
    async def test_network_stats_aggregation(
        self, client, valid_api_key, job_submit_payload, miner_register_payload
    ):
        """Test network stats aggregate multiple jobs and miners."""
        # Register 3 miners
        for i in range(3):
            payload = miner_register_payload.copy()
            payload["miner_id"] = f"miner-{i:03d}"
            await client.post(
                "/v1/miners/register",
                json=payload,
                headers={"X-API-Key": valid_api_key},
            )

        # Submit 5 jobs
        for i in range(5):
            payload = job_submit_payload.copy()
            payload["reward_gaia"] = 50.0 + i
            await client.post(
                "/v1/jobs/submit",
                json=payload,
                headers={"X-API-Key": valid_api_key},
            )

        # Get network stats
        response = await client.get(
            "/v1/network/stats",
            headers={"X-API-Key": valid_api_key},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_jobs"] == 5
        assert data["active_miners"] == 3

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
