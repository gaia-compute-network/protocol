# GAIA Token Economics

## Token Supply

- **Total Supply**: 21,000,000 GAIA (fixed, no inflation)
- **Decimals**: 18 (ERC-20 standard)

## Initial Distribution

| Recipient | Allocation | Vesting | Purpose |
|-----------|-----------|---------|---------|
| **Miner Rewards** | 50% (10.5M) | See vesting schedule | Incentivize compute and validation |
| **Ecosystem Fund** | 30% (6.3M) | Unlocked at genesis | Grants, development, research |
| **Genesis Participants** | 20% (4.2M) | 5-year linear vesting | Ceremony contributors (9 participants) |

No private sales, no ICO, no founder allocation.

## Burn-and-Mint Equilibrium

1. **Demand Phase**: Organizations submit environmental analysis tasks. They purchase GAIA tokens to pay compute fees.
2. **Burn Phase**: These tokens are sent to a burn address permanently, reducing total supply (deflation).
3. **Price Appreciation**: Declining supply + constant/growing demand = price appreciation.
4. **Mining Incentive**: Higher GAIA price makes mining more profitable; more nodes join.
5. **Mint Phase**: Miners receive freshly minted GAIA as block rewards for verified compute.
6. **Equilibrium**: Minting and burning naturally balance based on network demand.

Direction of effects:
- **High demand** -> More burns -> Deflation -> Higher price -> More mining -> More mints
- **Low demand** -> Fewer burns -> Less mining incentive -> Fewer mints

## Miner Vesting Schedule

| Tranche | Timing | Purpose |
|---------|--------|---------|
| **50% Immediate** | At reward issuance | Fund operations and hardware |
| **50% Over 90 Days** | Linear daily release | Prevent immediate sell pressure |

The 50/50 split prevents a dump-on-genesis attack where miners flood the market immediately, crashing the token price.

## Bank-Run Spiral Prevention

Three mechanisms guard against deflationary death spirals:

1. **Conviction Voting Lock-In**: Token holders voting on protocol parameters must lock tokens for the voting period (2 weeks), discouraging panic selling during governance.
2. **Oracle Anchoring**: The frozen ML oracle removes subjective uncertainty. Validators remain confident results are verifiable regardless of price.
3. **Sustainable Fee Structure**: Fees calibrated to remain profitable across a wide range of token prices. A validator earning 10 GAIA remains viable even if price drops 50%.

## Fee Structure

| Service | Fee | Destination |
|---------|-----|-------------|
| Task Submission | 0.1 GAIA per task | Protocol treasury |
| Compute | 0.1-10 GAIA (by model size) | Compute node operator |
| Validation | 0.05 GAIA per quorum | Validator nodes (split equally) |
| Oracle Query | Free | N/A |

## MiCA Classification

GAIA is classified as an **"other crypto-asset"** under **Title II** of EU MiCA (lightest regulatory framework).

**Not an EMT**: No fiat peg. Price floats freely.

**Not an ART**: No basket reference. No redemption promise.

**Why Title II**: GAIA is a utility token for computational services. Task submitters buy GAIA for compute access; miners earn GAIA as compensation. Supply is governed by protocol rules, not a single issuer.

Title II requires basic transparency, operational resilience, and governance disclosures — no reserve backing or redemption guarantees required.

### Jurisdictional Notes

| Jurisdiction | Classification |
|--------------|----------------|
| EU | Title II, MiCA |
| US | Utility token (no investment contract characteristics) |
| Switzerland | Utility token |
| Singapore | MAS utility token approval (anticipated) |

## Long-Term Supply Projections

Under Burn-and-Mint Equilibrium (illustrative):

| Period | Supply Range | Driver |
|--------|-------------|--------|
| Year 1 | ~21M (genesis release) | Early mining, low burn |
| Year 2-5 | 18M-21M | Demand growth accelerates burn |
| Year 5+ | 15M-18M | Stable equilibrium |

## Treasury

Protocol fees accrue to a community treasury governed by conviction voting. Possible uses:
- Ecosystem grants for environmental science orgs
- Infrastructure upgrades (oracle node subsidies)
- Bug bounties and security audits
- Outreach to conservation organizations

Treasury funds cannot be distributed to individuals for speculation.
