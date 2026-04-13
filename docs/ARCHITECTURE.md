# GAIA Protocol Architecture

## Node Types

### Compute Nodes
Compute nodes execute GPU inference tasks against environmental datasets. They receive a task description, load the appropriate ML model (via the frozen oracle), run inference, and submit results with cryptographic proof of execution. Compute nodes are rewarded for correct results but face slashing penalties for Byzantine behavior.

### Validator Nodes
Validator nodes verify the correctness of compute results using the Freivalds algorithm and quorum consensus. They perform efficient matrix verification (O(n²)) and compare outputs against reference datasets (GBIF, iNaturalist, Global Forest Watch). A minimum of 3 independent validators must reach consensus on each result.

### Oracle Nodes
Oracle nodes maintain the frozen ML model weights, distributed as a content-addressed hash commitment in the genesis block. They compare inference outputs against external scientific reference datasets (iNaturalist, GBIF, IUCN Red List, Global Forest Watch) and serve as ground truth for validation.

## Task Lifecycle

```
SUBMIT TASK
    |
ROUTE TO NODES (task load balancing, hardware matching)
    |
COMPUTE (GPU node executes inference)
    |
VALIDATOR QUORUM
    |-- Freivalds Verification (O(n2) probabilistic check)
    |-- >=3 independent validators required
    |-- Byzantine fault tolerance: up to 33% malicious nodes tolerated
    |
OUTPUT MATCHING (compare against reference datasets)
    |
CONSENSUS CHECK (unanimous validator agreement required)
    |
REWARD / SLASH
    |-- Validators: token reward for correct consensus
    |-- Compute node: token reward if validated
    |-- Slashing: misbehaving nodes lose collateral
```

## Frozen ML Oracle

The frozen ML oracle is the protocol's guarantee that scientific computation remains immutable and verifiable:

1. **Genesis Block Commitment**: At genesis ceremony, 9 trusted participants compute a cryptographic hash of the ML model weights.
2. **Distributed Hash**: The hash is embedded in the genesis block and distributed across the network.
3. **Hardware Destruction**: All original hardware used in the genesis ceremony is destroyed.
4. **Oracle Verification**: Oracle nodes verify that results match the committed weights via on-chain hash comparison.
5. **Oracle Updates**: Require a 90% conviction vote with a >=2 week voting period.

The frozen oracle prevents the protocol from becoming a "democracy of opinion." Scientific truth is anchored in verifiable computation, not subjective voting.

## Validation Stack

### 1. Freivalds Algorithm
- **Time Complexity**: O(n²) vs. O(n³) for full multiplication
- **Correctness Probability**: (1 - error_rate)^k where k is number of verification rounds
- **Typical Configuration**: k=40 rounds gives error probability < 2^(-40)

For environmental tasks, matrices represent inference operations (e.g., convolutional layer outputs). A validator samples random vectors, performs lightweight matrix-vector multiplications, and confirms the result matches the claimed computation.

### 2. Quorum Validation
- **Minimum Quorum**: >=3 independent validator nodes
- **Byzantine Fault Tolerance**: Up to 33% of validators can be malicious; consensus still holds
- **Agreement Requirement**: All validators in the quorum must reach the same conclusion
- **Timeout**: Validators failing to respond within 30 seconds are excluded and slashed

### 3. Output Matching
Validators compare compute outputs against reference datasets:
- **GBIF**: Global Biodiversity Information Facility — species occurrence data
- **iNaturalist**: Community-contributed observations with GPS coordinates
- **IUCN Red List**: Species threat status and habitat information
- **Global Forest Watch**: Deforestation and land-use change datasets

## ZK-Proof Roadmap

| Phase | Framework | Model Size | Proof Time | Status |
|-------|-----------|------------|------------|--------|
| 1 | EZKL | <44k params | 0.15-2.7s | Targeted |
| 2 | RISC Zero zkVM | 100k-10M params | Seconds-minutes | Planned |
| 3 | Modulus Labs | >10M params | Minutes-hours | Future |

## Genesis Ceremony

The genesis ceremony follows the Zcash model:

1. **9 participants** from >=5 different countries
2. **Isolated hardware** — freshly installed, no prior network history
3. **Sequential contributions** — each participant adds entropy from physical sources
4. **Hash publication** — final genesis hash is published and becomes immutable
5. **Hardware destruction** — all hardware physically destroyed post-ceremony
6. **Live-streamed** — entire ceremony publicly logged for audit

## Network Topology

```
Task Submitter
      |
Task Ingestion (Priority Queue)
      |
   [Compute Nodes] --- GPU inference, parallel
      |
   [Validator Nodes] --- Freivalds + quorum (>=3)
      |
   [Oracle Nodes] --- Reference dataset matching
      |
  Reward / Slash
```
