# GAIA Protocol — Technical Implementation

> *"Remove the trust requirement from environmental compute."*

## What Is GAIA?

GAIA is a decentralized GPU compute network for environmental science. It allows conservation organizations, researchers, and enterprises to submit ML inference jobs (species classification, deforestation detection, biodiversity indexing) and receive **cryptographically verified results** — without trusting any single server.

The protocol answers a question that matters: *How do you know the AI that classified 50,000 camera trap images wasn't lying?*

---

## Repository Structure

```
gaia-protocol-code/
├── contracts/                    # Solidity smart contracts
│   ├── GAIAToken.sol             # ERC-20, 21M cap, no post-genesis mint
│   ├── TaskRegistry.sol          # Job lifecycle management
│   ├── ValidationPool.sol        # Freivalds quorum verification
│   ├── RewardDistributor.sol     # 90-day linear vesting for miners
│   ├── ConvictionVoting.sol      # Time-weighted governance
│   ├── TimeLock.sol              # 18-month genesis authority expiry
│   ├── FrozenOracle.sol          # In-scope job classifier (immutable)
│   └── GAIAProtocol.sol          # System registry & emergency pause
│
├── node/                         # Off-chain node software (Python)
│   ├── miner_node.py             # Miner: receives jobs, computes, commits
│   ├── validator_node.py         # Validator: runs Freivalds, submits proof
│   └── api_server.py             # FastAPI REST API for requesters
│
├── tests/                        # Test suite
│   ├── test_freivalds.py         # 24 unit tests (Freivalds + crypto primitives)
│   └── test_integration.py       # 14 integration tests (full job lifecycle)
│
└── scripts/                      # Deployment and utility scripts
    ├── deploy.js                 # Hardhat deployment script
    └── genesis_ceremony.py       # Genesis ceremony coordinator
```

---

## The Core Cryptographic Insight

Every ML inference layer is a matrix multiplication: **W × X = Y**

**Freivalds' Algorithm (1977):** Pick a random vector r. If W×X = Y, then W(Xr) = Yr always. If W×X ≠ Y, then Pr[W(Xr) = Yr] ≤ ½. Run k rounds: error probability drops to 2⁻ᵏ.

**Cost:** O(n²) instead of O(n³). Verification is ~10× faster than recomputation.

**On GAIA:** 3 miners compute independently → submit result fingerprints → quorum consensus → Freivalds verifies → result on-chain in <1 second.

---

## Determinism Fix: Why INT32?

Different GPU architectures (NVIDIA A100 vs AMD MI300) produce float32 results that differ by ~1e-4. Without a fix, two honest miners would appear to disagree.

**Solution:** All miners quantize inputs to INT32 before computing. INT32 arithmetic is deterministic across all hardware. Two honest miners with the same inputs always produce the same fingerprint.

```python
from gaia_protocol.freivalds import quantize_to_int32
A_q, scale = quantize_to_int32(A_float32)
# A_q is now deterministic across any GPU architecture
```

---

## The Two-Layer Commitment Architecture

A critical design insight discovered during development:

```
commitment       = SHA-256(GAIA_COMMITMENT_V1  + job_id + miner_id + timestamp + result)
result_fingerprint = SHA-256(GAIA_RESULT_FINGERPRINT_V1 + job_id + result)
```

- **commitment** — unique per miner, prevents result-copying (miners commit before seeing each other's results)
- **result_fingerprint** — identical for any two miners with the same answer, used for quorum consensus

Without this separation, honest miners would always appear to disagree (their commitments differ because miner_id is included).

---

## Smart Contract Overview

| Contract | Purpose | Key Constraint |
|----------|---------|----------------|
| `GAIAToken` | ERC-20, 21M cap | No post-genesis mint, public burn |
| `TaskRegistry` | Job lifecycle | 5% burn on submission, IPFS inputs |
| `ValidationPool` | Freivalds quorum | Slashes dissenters, penalizes collusion |
| `RewardDistributor` | Miner payouts | 90-day linear vesting |
| `ConvictionVoting` | Governance | Time-weighted, flash-loan resistant |
| `TimeLock` | Genesis authority | Expires after 18 months, no override |
| `FrozenOracle` | Job type gate | 90% supermajority to update, once/decade |

---

## Running the Tests

```bash
# Install dependencies
pip install numpy pytest

# Unit tests (Freivalds + crypto primitives)
pytest tests/test_freivalds.py -v

# Integration tests (full job lifecycle)
pytest tests/test_integration.py -v

# All tests
pytest tests/ -v
# Expected: 38 passed
```

---

## Running the Demo

```bash
# Genesis demo (protocol proof of concept)
cd gaia_protocol/
python demo.py

# Miner node (demo mode)
python node/miner_node.py --demo

# Validator node (demo mode)
python node/validator_node.py --demo

# API server
pip install fastapi uvicorn
python node/api_server.py
# Open http://localhost:8000/docs for interactive API
```

---

## The Token Economics

```
Total supply:    21,000,000 GAIA (hard cap, like Bitcoin)
Burn rate:       5% of every job payment burned permanently
Miner share:     60% of post-burn payment (90-day linear vest)
Validator share: 25% of post-burn payment
Treasury:        15% of post-burn payment

Governance:      Conviction voting (time-weighted, 1yr ≈ 100× day-1 power)
Slashing:        50% of stake for dissenters, 100% for collusion suspects
```

---

## The Privacy Architecture

Miners **never see** raw input data:
- Images are quantized to INT32 matrices before transmission
- Metadata location is coarsened to ISO-3166 country code only
- GPS coordinates are encrypted with requester key
- Validators verify computation, not content

This means a GAIA miner cannot use camera trap data as a poaching map.

---

## The FrozenOracle: Constitutional Boundary

The FrozenOracle defines what GAIA can compute. It is a binary classifier: environmental science = in-scope, everything else = out-of-scope.

**Approved job types:**
- `species_identification` — camera trap / field image species classification
- `deforestation_detection` — satellite land-cover change detection
- `ocean_temperature_inference` — sea surface temperature trends
- `biodiversity_index` — GBIF / iNaturalist occurrence data
- `carbon_sequestration` — LiDAR / remote sensing estimation
- `acoustic_ecology` — bioacoustic species identification
- `wildfire_classification` — fire, smoke, air quality
- `marine_microplastics` — spectroscopy / image detection

**Permanently blocked:** financial models, facial recognition, medical diagnosis, surveillance.

The Oracle hash is committed at genesis. Updating requires 90%+ conviction voting supermajority, once per decade. There is no emergency override.

---

## Deployment

See `scripts/deploy.js` for the full Hardhat deployment script.

**Deployment order:**
1. `GAIAToken` → `TimeLock` (receives full supply)
2. `ConvictionVoting`
3. `FrozenOracle`
4. `RewardDistributor`
5. `ValidationPool`
6. `TaskRegistry`
7. `GAIAProtocol` (system registry)
8. Genesis ceremony: `oracle.initializeOracle(modelHash, modelCID)`
9. `timeLock` distributes initial allocations (40% miners, 20% ecosystem, 20% public, 10% treasury, 10% team)

After the genesis period (18 months), `TimeLock.revokeGenesisAuthority()` is called voluntarily — or authority expires automatically. The protocol becomes fully autonomous.

---

## CSRD Compliance

GAIA results are ESRS E4-compatible. Every verified job produces an on-chain record:

```json
{
  "protocol": "GAIA/1",
  "job_id": "job_...",
  "result_commitment": "0x...",
  "quorum": ["miner_1", "miner_2", "miner_3"],
  "freivalds_error_bound": 0.0009765625,
  "verified_at": 1776118163,
  "csrd_framework": "ESRS E4",
  "metadata": {
    "task": "species_identification",
    "location_country": "KGZ",
    "dataset": "snow_leopard_camera_batch_001"
  }
}
```

This record satisfies the "verified" requirement of CSRD's ESRS E4 biodiversity reporting standard.

---

## License

MIT License. The protocol is open source. The mission is not.

*Built by the GAIA Core Team — April 2026*
