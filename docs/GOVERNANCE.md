# GAIA Governance

## Core Principle

**The protocol governs, not people.**

GAIA's governance framework minimizes human discretion, prevents capture, and anchors decision-making in verifiable computation. Where possible, the protocol eliminates governance entirely by making decisions immutable or automatic.

## Frozen ML Oracle as Governance Mechanism

Environmental science should not be subject to democratic voting. A species detection model is either correct or incorrect based on ground truth (GBIF, iNaturalist), not consensus. The frozen oracle ensures scientific truth — not opinion — governs validation.

How it works:
1. At genesis, a cryptographic hash of the ML model weights is committed by 9 participants from >=5 countries.
2. The hash is embedded in the genesis block — immutable except via hard fork.
3. Oracle updates require 90% conviction vote + >=2 week voting period.
4. Validators always compare compute results against the current oracle hash. Mismatch = invalid.

## Conviction Voting

All governance decisions requiring human choice use conviction voting.

### Mechanism

| Conviction Level | Lock Duration | Voting Power Multiplier |
|-----------------|---------------|------------------------|
| 0 (new voter) | Just locked | 1x |
| 1 | 1 prior period | 1.5x |
| 2 | 2+ prior periods | 3x |
| 3 | 3+ prior periods | 6x |
| 4 | 4+ prior periods | 10x |

- Token holders lock GAIA for the entire voting period (2 weeks minimum).
- Vote weight = tokens locked x conviction multiplier.
- A vote passes at 51% approval with >=10% of total supply participating.

### Why Conviction Voting?

**Prevents flash attacks**: Borrowed tokens cannot vote — lock-in for 2 weeks makes attacks economically irrational.

**Rewards long-term alignment**: Participants with consistent lock history gain disproportionate voting power.

**Prevents governance surprises**: Sudden token movements (exchange listing, whale purchase) cannot trigger instant governance changes.

## COCM (Connection-Oriented Cluster Matching)

An upgrade to quadratic voting that prevents collusion. COCM:
1. Groups voters by on-chain interaction history (shared validators, tasks, etc.)
2. Reduces weight of votes from voters exhibiting colluding behavior (identical voting across proposals)
3. Uses graph analysis to identify and down-weight sybil clusters

Status: Research-grade mechanism under finalization.

## What Is Governable

Community conviction voting applies to:

1. **Fee Parameters**: Gas fees, compute costs, validator rewards (upper bound: 5 GAIA/task max)
2. **Oracle Registry Updates**: Adding scientific reference datasets (requires >=90% conviction)
3. **Ecosystem Fund Allocation**: Treasury grants for environmental science
4. **Network Parameters**: Quorum size, validator timeout, slash amounts (within bounds)

Proposal timeline: 2-week discussion + 1-week voting + 1-week timelock before execution.

## What Is NOT Governable

These protocol constants are permanently immutable:

| Constant | Reason |
|----------|--------|
| Genesis Hash | Foundation of all validation trust |
| Total Token Supply (21M cap) | Prevents inflation attacks |
| Burn-and-Mint Equilibrium Logic | Core economic mechanism |
| Time-Lock Expiry (18 months) | Founder privilege cannot be extended |
| Freivalds Algorithm Parameters | Core security mechanism |
| Conviction Voting Structure | Governance cannot vote itself away |

## Foundation Oversight (Months 1-18)

A temporary 5-of-9 multisig foundation oversees the protocol during the Foundation Phase.

**Composition**:
- 5 of 9 signers required for any action
- >=5 different countries represented
- No single country holds >2 of 9 seats
- No veto power over community conviction votes

**Foundation Powers**:
- Emergency network pause (max 72 hours) for critical security vulnerabilities
- Propose oracle weight updates (community must still ratify with 90% conviction)
- Release non-consensus-affecting software patches
- Mediate validator disputes (community can override)

**Foundation Constraints**:
- Cannot mint tokens
- Cannot change protocol constants
- Cannot spend ecosystem treasury
- Cannot create new administrative roles

## Time-Lock: Automatic Expiry

All founder privileges expire **automatically at month 18** post-genesis via a hardcoded time-lock smart contract:

- Multisig can no longer pause the network
- Multisig can no longer propose oracle updates
- All administrative keys are burned
- Protocol becomes fully autonomous

**This expiry is non-negotiable.** It cannot be extended, delayed, or voted away. It is encoded in the genesis block.

## Governance Lifecycle

```
Month 1-6: Foundation Phase
  5-of-9 multisig active. Community conviction voting enabled.
  Community vote supersedes foundation at >=90% conviction.

Month 6-18: Transition Phase
  Foundation oversight continues (diminishing).
  Community governs non-critical parameters.
  Oracle updates require community >=90% conviction.

Month 18+: Autonomous Phase
  Time-lock expires. Foundation dissolved.
  Only community conviction voting remains.
  Protocol is fully decentralized.
```

## Security Properties

- Conviction voting prevents flash attacks (2-week lock requirement)
- 5-of-9 multisig (55.6% agreement threshold) prevents single-actor capture
- Geographic distribution (>=5 countries) prevents regional regulatory capture
- Time-lock enforces hard expiry of founder privileges
- Immutable constants prevent centralization via governance attack
