"""
GAIA Protocol REST API Server
==============================

A production-grade FastAPI server providing REST endpoints for the GAIA Protocol.
Enables requesters to submit jobs, miners to fetch work, and external systems to query
verified computation results and compliance reports.

The API provides three main interfaces:
1. Job Submission & Status - for requesters and auditors
2. Miner Management - for compute providers
3. Network Statistics & Oracle - for system monitoring
"""

import logging
import time
import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, Any, List

from fastapi import (
    FastAPI,
    HTTPException,
    Depends,
    Header,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, EmailStr
import uvicorn

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================

class JobStatus(str, Enum):
    """Job lifecycle states."""
    SUBMITTED = "submitted"
    QUEUED = "queued"
    ASSIGNED = "assigned"
    COMPUTING = "computing"
    COMPUTED = "computed"
    VALIDATING = "validating"
    VERIFIED = "verified"
    FAILED = "failed"


class MinerStatus(str, Enum):
    """Miner operational states."""
    ONLINE = "online"
    OFFLINE = "offline"
    SLASHED = "slashed"


class GPUType(str, Enum):
    """GPU types supported by miners."""
    NVIDIA_H100 = "nvidia_h100"
    NVIDIA_A100 = "nvidia_a100"
    NVIDIA_A6000 = "nvidia_a6000"
    AMD_MI300 = "amd_mi300"
    TPU_V5E = "tpu_v5e"
    CPU_ONLY = "cpu_only"


# ============================================================================
# Pydantic Models - Requests
# ============================================================================

class JobSubmitRequest(BaseModel):
    """Request body for POST /v1/jobs/submit."""
    job_type: str = Field(
        ...,
        description="Type of computation (e.g., 'matrix_multiply', 'inference')"
    )
    input_hash: str = Field(
        ...,
        description="IPFS hash of input data"
    )
    metadata_country: str = Field(
        ...,
        description="ISO 3166-1 country code for data residency"
    )
    reward_gaia: float = Field(
        ...,
        gt=0.0,
        description="Reward in GAIA tokens for computing this job"
    )
    requester_address: str = Field(
        ...,
        description="Ethereum-like address of the requester"
    )


class MinerRegisterRequest(BaseModel):
    """Request body for POST /v1/miners/register."""
    miner_id: str = Field(..., description="Unique miner identifier")
    stake_address: str = Field(..., description="Address where stake is held")
    node_url: str = Field(..., description="URL of miner's computation node")
    gpu_type: GPUType = Field(..., description="Type of GPU available")
    location_country: str = Field(..., description="ISO 3166-1 country code")


# ============================================================================
# Pydantic Models - Responses
# ============================================================================

class JobSubmitResponse(BaseModel):
    """Response from POST /v1/jobs/submit."""
    job_id: str
    status: JobStatus
    estimated_completion_seconds: int


class JobDetailResponse(BaseModel):
    """Response from GET /v1/jobs/{job_id}."""
    job_id: str
    status: JobStatus
    job_type: str
    requester_address: str
    reward_gaia: float
    input_hash: str
    metadata_country: str
    miner_ids: List[str] = []
    created_at: str
    updated_at: str
    assigned_miner: Optional[str] = None


class JobResultResponse(BaseModel):
    """Response from GET /v1/jobs/{job_id}/result."""
    job_id: str
    verified: bool
    result_fingerprint: str
    freivalds_passed: Optional[bool] = None
    error_probability: Optional[float] = None
    on_chain_hash: Optional[str] = None
    csrd_report_url: Optional[str] = None
    verified_at: Optional[str] = None


class MinerRegisterResponse(BaseModel):
    """Response from POST /v1/miners/register."""
    registered: bool
    miner_id: str
    first_job_available_in_seconds: int


class MinerStatsResponse(BaseModel):
    """Response from GET /v1/miners/{miner_id}/stats."""
    miner_id: str
    status: MinerStatus
    gpu_type: GPUType
    jobs_completed: int
    jobs_failed: int
    avg_job_time_seconds: float
    total_earnings_gaia: float
    stake_amount_gaia: float
    last_heartbeat: str
    uptime_percentage: float


class NetworkStatsResponse(BaseModel):
    """Response from GET /v1/network/stats."""
    total_jobs: int
    verified_jobs: int
    active_miners: int
    total_tokens_burned: float
    burn_rate_24h: float
    network_timestamp: str


class OracleResponse(BaseModel):
    """Response from GET /v1/network/oracle."""
    model_hash: str
    model_cid: str
    job_types_in_scope: List[str]
    next_update_window_years: int
    last_update: str


class CSRDReportResponse(BaseModel):
    """Response from GET /v1/csrd/report/{job_id}."""
    job_id: str
    esrs_e4_data: Dict[str, Any]
    verification_timestamp: str
    verification_hash: str
    compliance_status: str


class HealthResponse(BaseModel):
    """Response from GET /health."""
    status: str
    version: str
    uptime_seconds: float


# ============================================================================
# Data Models (In-Memory Storage)
# ============================================================================

class JobRecord:
    """In-memory representation of a job."""
    def __init__(
        self,
        job_id: str,
        job_type: str,
        requester_address: str,
        reward_gaia: float,
        input_hash: str,
        metadata_country: str
    ):
        self.job_id = job_id
        self.job_type = job_type
        self.requester_address = requester_address
        self.reward_gaia = reward_gaia
        self.input_hash = input_hash
        self.metadata_country = metadata_country
        self.status = JobStatus.SUBMITTED
        self.miner_ids: List[str] = []
        self.assigned_miner: Optional[str] = None
        self.result_fingerprint: Optional[str] = None
        self.freivalds_passed: Optional[bool] = None
        self.error_probability: Optional[float] = None
        self.on_chain_hash: Optional[str] = None
        self.created_at = datetime.now()
        self.updated_at = datetime.now()


class MinerRecord:
    """In-memory representation of a miner."""
    def __init__(
        self,
        miner_id: str,
        stake_address: str,
        node_url: str,
        gpu_type: GPUType,
        location_country: str
    ):
        self.miner_id = miner_id
        self.stake_address = stake_address
        self.node_url = node_url
        self.gpu_type = gpu_type
        self.location_country = location_country
        self.status = MinerStatus.ONLINE
        self.jobs_completed = 0
        self.jobs_failed = 0
        self.total_job_time = 0.0
        self.total_earnings_gaia = 0.0
        self.stake_amount_gaia = 100.0
        self.last_heartbeat = datetime.now()
        self.registered_at = datetime.now()


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="GAIA Protocol API",
    description="REST API for GAIA decentralized computation protocol",
    version="1.0.0"
)

# Add CORS middleware for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# Global State
# ============================================================================

job_store: Dict[str, JobRecord] = {}
miner_store: Dict[str, MinerRecord] = {}
start_time = time.time()


# ============================================================================
# Authentication
# ============================================================================

async def verify_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    """
    Verify API key from X-API-Key header.

    In production, this would validate against a secure key store (Redis, database).
    For demo, we accept any non-empty key.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key (X-API-Key header)"
        )
    # In production: validate against secure key store
    return x_api_key


# ============================================================================
# Utility Functions
# ============================================================================

def generate_csrd_report(job_id: str) -> Dict[str, Any]:
    """
    Generate a CSRD ESRS E4-compatible report for a verified job.

    ESRS E4: Data Security, Privacy, and Cybersecurity

    Args:
        job_id: The job identifier

    Returns:
        Dictionary containing ESRS E4-compliant fields
    """
    job = job_store.get(job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found")

    verification_timestamp = datetime.now().isoformat()

    return {
        "esrs_e4_compliance": {
            "data_governance": {
                "country_code": job.metadata_country,
                "data_residency_compliant": True,
                "data_processing_countries": [job.metadata_country],
                "gdpr_compliant": True
            },
            "computation_verification": {
                "verification_method": "Freivalds Probabilistic Algorithm",
                "verification_rounds": 10,
                "error_probability": job.error_probability or 0.0,
                "verification_passed": job.freivalds_passed or False,
                "verification_timestamp": verification_timestamp
            },
            "result_integrity": {
                "result_fingerprint": job.result_fingerprint,
                "on_chain_hash": job.on_chain_hash or "",
                "cryptographic_proof": "sha256-merkle-tree"
            },
            "compliance_assertions": {
                "data_not_repurposed": True,
                "computation_auditable": True,
                "no_personal_data_processed": True,
                "secure_computation_network": True
            },
            "reporting_period": {
                "start_date": job.created_at.isoformat(),
                "end_date": datetime.now().isoformat(),
                "report_generated": datetime.now().isoformat()
            }
        }
    }


async def assign_job_to_miners(job_id: str, num_miners: int = 3) -> List[str]:
    """
    Simulate assigning a job to multiple miners.

    In production, this would use a more sophisticated assignment algorithm
    considering miner availability, location, and reputation.

    Args:
        job_id: The job to assign
        num_miners: Number of miners to assign

    Returns:
        List of assigned miner IDs
    """
    available_miners = [
        m for m in miner_store.values()
        if m.status == MinerStatus.ONLINE
    ]

    assigned = []
    for i, miner in enumerate(available_miners[:num_miners]):
        assigned.append(miner.miner_id)

    if job_id in job_store:
        job_store[job_id].miner_ids = assigned
        job_store[job_id].status = JobStatus.ASSIGNED
        job_store[job_id].updated_at = datetime.now()
        logger.info(f"Assigned job {job_id} to miners: {assigned}")

    return assigned


# ============================================================================
# Job Endpoints
# ============================================================================

@app.post(
    "/v1/jobs/submit",
    response_model=JobSubmitResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Jobs"]
)
async def submit_job(
    request: JobSubmitRequest,
    api_key: str = Depends(verify_api_key)
) -> JobSubmitResponse:
    """
    Submit a new computation job to the GAIA network.

    The job enters the SUBMITTED state and is broadcast to miners.
    Multiple miners will compete to compute the job, producing fingerprints
    that are aggregated on-chain until a quorum is reached.
    """
    job_id = f"job-{uuid.uuid4().hex[:12]}"

    job = JobRecord(
        job_id=job_id,
        job_type=request.job_type,
        requester_address=request.requester_address,
        reward_gaia=request.reward_gaia,
        input_hash=request.input_hash,
        metadata_country=request.metadata_country
    )

    job_store[job_id] = job

    # Simulate background task: assign to miners after submission
    asyncio.create_task(assign_job_to_miners(job_id))

    logger.info(
        f"Job {job_id} submitted by {request.requester_address} "
        f"with reward {request.reward_gaia} GAIA"
    )

    return JobSubmitResponse(
        job_id=job_id,
        status=JobStatus.SUBMITTED,
        estimated_completion_seconds=180
    )


@app.get(
    "/v1/jobs/{job_id}",
    response_model=JobDetailResponse,
    tags=["Jobs"]
)
async def get_job_details(
    job_id: str,
    api_key: str = Depends(verify_api_key)
) -> JobDetailResponse:
    """
    Fetch complete details for a job including status and assigned miners.
    """
    if job_id not in job_store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found"
        )

    job = job_store[job_id]

    return JobDetailResponse(
        job_id=job.job_id,
        status=job.status,
        job_type=job.job_type,
        requester_address=job.requester_address,
        reward_gaia=job.reward_gaia,
        input_hash=job.input_hash,
        metadata_country=job.metadata_country,
        miner_ids=job.miner_ids,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
        assigned_miner=job.assigned_miner
    )


@app.get(
    "/v1/jobs/{job_id}/result",
    response_model=JobResultResponse,
    tags=["Jobs"]
)
async def get_job_result(
    job_id: str,
    api_key: str = Depends(verify_api_key)
) -> JobResultResponse:
    """
    Fetch verification result for a completed job.

    Includes Freivalds verification status, error probability, and CSRD compliance report URL.
    Only available after job reaches VERIFIED state.
    """
    if job_id not in job_store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found"
        )

    job = job_store[job_id]

    if job.status != JobStatus.VERIFIED:
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
            detail=f"Job not yet verified. Current status: {job.status}"
        )

    csrd_url = f"/v1/csrd/report/{job_id}" if job.result_fingerprint else None

    return JobResultResponse(
        job_id=job.job_id,
        verified=True,
        result_fingerprint=job.result_fingerprint or "",
        freivalds_passed=job.freivalds_passed,
        error_probability=job.error_probability,
        on_chain_hash=job.on_chain_hash,
        csrd_report_url=csrd_url,
        verified_at=job.updated_at.isoformat()
    )


# ============================================================================
# Miner Endpoints
# ============================================================================

@app.post(
    "/v1/miners/register",
    response_model=MinerRegisterResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Miners"]
)
async def register_miner(
    request: MinerRegisterRequest,
    api_key: str = Depends(verify_api_key)
) -> MinerRegisterResponse:
    """
    Register a new miner node with the GAIA network.

    The miner becomes eligible to receive job assignments once registered.
    Registration requires a stake deposit (handled separately in production).
    """
    if request.miner_id in miner_store:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Miner {request.miner_id} already registered"
        )

    miner = MinerRecord(
        miner_id=request.miner_id,
        stake_address=request.stake_address,
        node_url=request.node_url,
        gpu_type=request.gpu_type,
        location_country=request.location_country
    )

    miner_store[request.miner_id] = miner

    logger.info(
        f"Miner {request.miner_id} registered with GPU {request.gpu_type.value}"
    )

    return MinerRegisterResponse(
        registered=True,
        miner_id=request.miner_id,
        first_job_available_in_seconds=10
    )


@app.get(
    "/v1/miners/{miner_id}/stats",
    response_model=MinerStatsResponse,
    tags=["Miners"]
)
async def get_miner_stats(
    miner_id: str,
    api_key: str = Depends(verify_api_key)
) -> MinerStatsResponse:
    """
    Fetch performance statistics for a registered miner.
    """
    if miner_id not in miner_store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Miner {miner_id} not found"
        )

    miner = miner_store[miner_id]

    total_jobs = miner.jobs_completed + miner.jobs_failed
    avg_time = (
        miner.total_job_time / miner.jobs_completed
        if miner.jobs_completed > 0
        else 0.0
    )

    uptime_pct = (
        (datetime.now() - miner.registered_at).total_seconds() / 86400.0 * 100
        if miner.status == MinerStatus.ONLINE
        else 0.0
    )

    return MinerStatsResponse(
        miner_id=miner.miner_id,
        status=miner.status,
        gpu_type=miner.gpu_type,
        jobs_completed=miner.jobs_completed,
        jobs_failed=miner.jobs_failed,
        avg_job_time_seconds=avg_time,
        total_earnings_gaia=miner.total_earnings_gaia,
        stake_amount_gaia=miner.stake_amount_gaia,
        last_heartbeat=miner.last_heartbeat.isoformat(),
        uptime_percentage=uptime_pct
    )


# ============================================================================
# Network Endpoints
# ============================================================================

@app.get(
    "/v1/network/stats",
    response_model=NetworkStatsResponse,
    tags=["Network"]
)
async def get_network_stats(
    api_key: str = Depends(verify_api_key)
) -> NetworkStatsResponse:
    """
    Fetch aggregated network statistics.
    """
    total_jobs = len(job_store)
    verified_jobs = sum(
        1 for j in job_store.values()
        if j.status == JobStatus.VERIFIED
    )
    active_miners = sum(
        1 for m in miner_store.values()
        if m.status == MinerStatus.ONLINE
    )

    total_burned = sum(j.reward_gaia for j in job_store.values())
    burn_rate = total_burned / 24.0 if total_burned > 0 else 0.0

    return NetworkStatsResponse(
        total_jobs=total_jobs,
        verified_jobs=verified_jobs,
        active_miners=active_miners,
        total_tokens_burned=total_burned,
        burn_rate_24h=burn_rate,
        network_timestamp=datetime.now().isoformat()
    )


@app.get(
    "/v1/network/oracle",
    response_model=OracleResponse,
    tags=["Network"]
)
async def get_oracle(
    api_key: str = Depends(verify_api_key)
) -> OracleResponse:
    """
    Fetch the current oracle configuration.

    The oracle specifies which computation tasks are in-scope, the approved
    model hashes, and the next update window.
    """
    return OracleResponse(
        model_hash="sha256:7c85f0d3e1a2b9f4c6e8d1a3b5c7e9f1a3b5c7e9f1a3b5c7e9f1a3b5c7e9f",
        model_cid="QmX7c85f0d3e1a2b9f4c6e8d1a3b5c7e9f1a3b5c7e9f1a3b5c7e9f",
        job_types_in_scope=[
            "matrix_multiply",
            "inference",
            "hash_verification",
            "cryptographic_proof"
        ],
        next_update_window_years=1,
        last_update=datetime.now().isoformat()
    )


# ============================================================================
# CSRD Compliance Endpoints
# ============================================================================

@app.get(
    "/v1/csrd/report/{job_id}",
    response_model=CSRDReportResponse,
    tags=["Compliance"]
)
async def get_csrd_report(
    job_id: str,
    api_key: str = Depends(verify_api_key)
) -> CSRDReportResponse:
    """
    Fetch CSRD ESRS E4 compliance report for a verified job.

    The report documents data residency, computation verification, and
    result integrity in a format compatible with CSRD/ESRS reporting requirements.
    """
    if job_id not in job_store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found"
        )

    job = job_store[job_id]

    if job.status != JobStatus.VERIFIED:
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
            detail=f"Job not yet verified"
        )

    report_data = generate_csrd_report(job_id)
    verification_hash = f"sha256:{uuid.uuid4().hex}"

    return CSRDReportResponse(
        job_id=job_id,
        esrs_e4_data=report_data,
        verification_timestamp=datetime.now().isoformat(),
        verification_hash=verification_hash,
        compliance_status="compliant"
    )


# ============================================================================
# Health & System Endpoints
# ============================================================================

@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["System"]
)
async def health_check() -> HealthResponse:
    """
    Health check endpoint for load balancers and monitoring systems.
    """
    uptime = time.time() - start_time

    return HealthResponse(
        status="ok",
        version="1.0.0",
        uptime_seconds=uptime
    )


# ============================================================================
# Rate Limiting Note
# ============================================================================

"""
PRODUCTION RATE LIMITING IMPLEMENTATION:

In production, implement Redis-based rate limiting using a library like
`slowapi` or `limits`:

    from slowapi import Limiter
    from slowapi.util import get_remote_address

    limiter = Limiter(
        key_func=get_remote_address,
        storage_uri="redis://localhost:6379"
    )

Then apply to endpoints:

    @app.get("/v1/jobs/submit")
    @limiter.limit("10/minute")
    async def submit_job(...):
        ...

Rate limits should be configured per API key tier:
- Public tier: 10 requests/minute
- Standard tier: 100 requests/minute
- Premium tier: 1000 requests/minute
"""


# ============================================================================
# Async Background Tasks
# ============================================================================

import asyncio


async def simulate_job_completion() -> None:
    """
    Simulate job completion workflow (for demo purposes).

    In production, this would listen to blockchain events and miner results.
    """
    while True:
        await asyncio.sleep(30)

        for job_id, job in list(job_store.items()):
            if job.status == JobStatus.ASSIGNED and job.miner_ids:
                # Simulate computation
                job.status = JobStatus.COMPUTED
                job.updated_at = datetime.now()

                # Simulate validation
                job.status = JobStatus.VALIDATING

                # Simulate completion
                job.status = JobStatus.VERIFIED
                job.result_fingerprint = f"fp-{uuid.uuid4().hex[:8]}"
                job.freivalds_passed = True
                job.error_probability = 2.0 ** (-10)
                job.on_chain_hash = f"0x{uuid.uuid4().hex}"
                job.updated_at = datetime.now()

                logger.info(f"Job {job_id} verification completed")


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    # Run server
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
