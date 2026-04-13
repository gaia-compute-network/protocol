# GAIA Protocol — Developer Documentation

This repository contains the protocol specification, architecture documentation, and governance rules for the GAIA decentralized GPU-compute network for environmental science.

## Repository Structure

```
protocol/
├── README.md              # This file
├── CONTRIBUTING.md        # How to contribute
├── CODE_OF_CONDUCT.md     # Community standards
└── docs/
    ├── ARCHITECTURE.md    # System architecture & node types
    ├── TOKEN_ECONOMICS.md # GAIA token, Burn-and-Mint, MiCA
    └── GOVERNANCE.md      # Conviction Voting, Oracle, Multisig
```

## Quick Links

- [Architecture Overview](docs/ARCHITECTURE.md)
- [Token Economics](docs/TOKEN_ECONOMICS.md)
- [Governance](docs/GOVERNANCE.md)
- [Contributing](CONTRIBUTING.md)
- [Whitepaper](https://github.com/gaia-compute-network/whitepaper)

## What is GAIA?

GAIA is a protocol for distributed, verifiable GPU computation applied to environmental science. The network allows conservation organizations (Snow Leopard Trust, Elephant Listening Project, Rainforest Connection) to submit ML inference tasks — species identification, bioacoustic analysis, camera trap classification — and receive results verified by independent nodes using Freivalds' algorithm and Byzantine fault-tolerant quorum consensus.

Key properties:

- **No founder**: Genesis Ceremony (Zcash Powers-of-Tau model) with 9 participants, 5 countries, hardware destroyed post-ceremony
- **Frozen Oracle**: ML weights committed in genesis block, immutable unless 90%+ fork majority
- **Time-Lock**: All initialization privileges expire automatically 18 months post-genesis
- **21M token cap**: No inflation, Burn-and-Mint Equilibrium
- **MiCA Tier II**: "other crypto-assets" — lightest EU regulatory burden

## Protocol Status

| Phase | Description | Status |
|-------|-------------|--------|
| -1 | Foundation (this repo) | In Progress |
| 0 | Genesis Ceremony | Pending |
| 1 | Core Network Launch | Pending |
| 2 | ZK-Proof Integration (EZKL) | Pending |
| 3 | Oracle Governance | Pending |

## License

Apache License 2.0
