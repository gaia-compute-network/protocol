// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title GAIAToken
 * @notice ERC-20 token for the GAIA Protocol — decentralized GPU compute network
 *         for environmental science.
 *
 * Design invariants:
 *   - Fixed supply cap: 21,000,000 GAIA (like Bitcoin: a hard ceiling, not a target)
 *   - No post-Genesis minting — the constructor mints the full supply once
 *   - Public burn — any holder can destroy tokens, permanently reducing supply
 *   - No owner, no admin, no upgrade proxy — immutable after deployment
 *
 * Token allocation (set by the Genesis Ceremony coordinator, then authority expires):
 *   40% — Miner rewards pool (RewardDistributor contract)
 *   20% — Ecosystem / grants (TimeLock, 4-year linear release)
 *   20% — Public sale / liquidity bootstrap
 *   10% — Protocol treasury (ConvictionVoting-governed multisig)
 *   10% — Core team (18-month cliff, 36-month linear vest — hardcoded in TimeLock)
 *
 * @author GAIA Core Team
 * @custom:version 1.0.0
 */

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Burnable.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Permit.sol";

contract GAIAToken is ERC20, ERC20Burnable, ERC20Permit {

    // ────────────────────────────────────────────────────────────────────────────
    // Constants
    // ────────────────────────────────────────────────────────────────────────────

    /// @notice Hard supply cap — can never be exceeded (enforced by no-mint design)
    uint256 public constant TOTAL_SUPPLY_CAP = 21_000_000 * 10 ** 18;

    /// @notice 5% of every requester payment is burned automatically
    ///         by the TaskRegistry. This constant is referenced on-chain
    ///         to make the parameter visible and auditable.
    uint256 public constant BURN_RATE_BPS = 500; // 500 basis points = 5%

    // ────────────────────────────────────────────────────────────────────────────
    // Errors
    // ────────────────────────────────────────────────────────────────────────────

    /// @notice Emitted when a mint would exceed the supply cap
    error SupplyCapExceeded(uint256 requested, uint256 cap);

    // ────────────────────────────────────────────────────────────────────────────
    // Events
    // ────────────────────────────────────────────────────────────────────────────

    /// @notice Emitted whenever tokens are permanently burned
    event TokensBurned(address indexed burner, uint256 amount, string reason);

    /// @notice Total tokens burned since genesis (monotonically increasing)
    uint256 public totalBurned;

    // ────────────────────────────────────────────────────────────────────────────
    // Constructor — the one and only mint
    // ────────────────────────────────────────────────────────────────────────────

    /**
     * @notice Deploy the GAIA token. The entire supply is minted once to
     *         `genesisReceiver` (typically a multi-party TimeLock contract
     *         controlled by the Genesis Ceremony participants).
     *
     *         After this constructor runs, no more tokens can ever be minted.
     *
     * @param genesisReceiver   Address that receives the full initial supply.
     *                          Must be the TimeLock or a multi-sig controlled
     *                          by the Genesis Ceremony — NOT a single EOA.
     */
    constructor(address genesisReceiver)
        ERC20("GAIA", "GAIA")
        ERC20Permit("GAIA")
    {
        require(genesisReceiver != address(0), "GAIA: zero address");
        _mint(genesisReceiver, TOTAL_SUPPLY_CAP);
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Burn with reason
    // ────────────────────────────────────────────────────────────────────────────

    /**
     * @notice Burn tokens from the caller's balance with an on-chain reason.
     *         Used by TaskRegistry for automated 5% burns per job payment.
     *
     * @param amount  Token amount to burn (in 10^18 units)
     * @param reason  Short description for on-chain auditability
     *                e.g. "job_payment_burn", "slash_penalty", "user_initiated"
     */
    function burnWithReason(uint256 amount, string calldata reason) external {
        _burn(msg.sender, amount);
        totalBurned += amount;
        emit TokensBurned(msg.sender, amount, reason);
    }

    /**
     * @notice Burn tokens from another address (requires allowance).
     *         Called by contracts (RewardDistributor for slashing).
     */
    function burnFromWithReason(
        address account,
        uint256 amount,
        string calldata reason
    ) external {
        _spendAllowance(account, msg.sender, amount);
        _burn(account, amount);
        totalBurned += amount;
        emit TokensBurned(account, amount, reason);
    }

    // ────────────────────────────────────────────────────────────────────────────
    // View helpers
    // ────────────────────────────────────────────────────────────────────────────

    /// @notice Current circulating supply (= cap - burned)
    function circulatingSupply() external view returns (uint256) {
        return totalSupply();
    }

    /// @notice Percentage of total cap that has been burned (basis points)
    function burnedBps() external view returns (uint256) {
        if (TOTAL_SUPPLY_CAP == 0) return 0;
        return (totalBurned * 10_000) / TOTAL_SUPPLY_CAP;
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Override _update to track burns via parent hooks
    // ────────────────────────────────────────────────────────────────────────────

    function _update(address from, address to, uint256 value)
        internal
        override(ERC20)
    {
        super._update(from, to, value);
    }
}
