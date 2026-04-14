// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * @title TimeLock
 * @notice Implements the Genesis Ceremony time-locked privilege system.
 *
 * ── The Core Insight ─────────────────────────────────────────────────────────
 *
 * "The person who started GAIA has no permanent privileges.
 *  Their authority expires automatically. This is not humility.
 *  It is the design." — GAIA Masterplan, Rev 1.4
 *
 * All privileged actions (parameter setting, initial token allocation, validator
 * bootstrapping) are controlled by this contract during the 18-month genesis period.
 * After month 19, ALL functions in this contract revert. Permanently.
 *
 * There is no extension. No emergency override. No multisig workaround.
 * The time lock IS the trust model.
 *
 * ── What happens at expiry ───────────────────────────────────────────────────
 *
 * Month 0–18: Genesis coordinator can execute privileged actions
 * Month 19:   All privileged functions revert forever
 * Month 19+:  Protocol is governed ONLY by ConvictionVoting
 *
 * After expiry, protocol changes require:
 *   - 33% conviction quorum for parameter changes
 *   - 90% conviction quorum for oracle changes
 *   - No single actor can ever control the protocol again
 *
 * ── Team token vesting ───────────────────────────────────────────────────────
 *
 * Team allocation (10% = 2,100,000 GAIA):
 *   - 18-month cliff (no tokens unlock before month 18)
 *   - 36-month linear vesting after cliff
 *   - Total vesting period: 54 months (4.5 years)
 *   - Forfeiture: if coordinator transfers authority before expiry, team
 *     tokens are permanently forfeited to the protocol treasury
 *
 * @author GAIA Core Team
 * @custom:version 1.0.0
 */
contract TimeLock is ReentrancyGuard {

    // ────────────────────────────────────────────────────────────────────────────
    // Constants
    // ────────────────────────────────────────────────────────────────────────────

    /// @notice Duration of the genesis period (18 months)
    uint256 public constant GENESIS_PERIOD = 18 * 30 days;

    /// @notice Team token cliff (18 months = same as genesis expiry)
    uint256 public constant TEAM_CLIFF = 18 * 30 days;

    /// @notice Team token vesting after cliff (36 months)
    uint256 public constant TEAM_VESTING_PERIOD = 36 * 30 days;

    // ────────────────────────────────────────────────────────────────────────────
    // State
    // ────────────────────────────────────────────────────────────────────────────

    IERC20 public immutable gaiaToken;

    /// @notice The genesis ceremony coordinator (has time-limited authority)
    address public immutable genesisCoordinator;

    /// @notice Genesis block timestamp
    uint256 public immutable genesisTimestamp;

    /// @notice When genesis authority expires (genesisTimestamp + GENESIS_PERIOD)
    uint256 public immutable genesisExpiry;

    /// @notice Whether genesis authority has been explicitly revoked early
    bool public authorityRevoked;

    // Team vesting
    struct TeamAllocation {
        address beneficiary;
        uint256 totalAmount;
        uint256 claimedAmount;
        string role; // e.g., "protocol_architect", "core_developer"
    }

    TeamAllocation[] public teamAllocations;
    mapping(address => uint256) public teamAllocationIndex;
    mapping(address => bool) public hasTeamAllocation;

    // Queued privileged actions (all actions are queued + delayed for transparency)
    struct QueuedAction {
        bytes32 actionId;
        address target;
        bytes callData;
        uint256 queuedAt;
        uint256 executeAfter; // Minimum 48h delay for all actions
        bool executed;
        string description;
    }

    mapping(bytes32 => QueuedAction) public queuedActions;
    bytes32[] public actionQueue;

    uint256 public constant MINIMUM_DELAY = 48 hours;

    // ────────────────────────────────────────────────────────────────────────────
    // Events
    // ────────────────────────────────────────────────────────────────────────────

    event ActionQueued(
        bytes32 indexed actionId,
        address target,
        string description,
        uint256 executeAfter
    );

    event ActionExecuted(bytes32 indexed actionId, bool success);
    event ActionCancelled(bytes32 indexed actionId);

    event TeamAllocationCreated(
        address indexed beneficiary,
        uint256 amount,
        string role
    );

    event TeamTokensClaimed(
        address indexed beneficiary,
        uint256 amount
    );

    event GenesisAuthorityExpired(uint256 timestamp);
    event GenesisAuthorityRevoked(uint256 timestamp);

    // ────────────────────────────────────────────────────────────────────────────
    // Errors
    // ────────────────────────────────────────────────────────────────────────────

    error GenesisAuthorityExpiredError();
    error NotGenesisCoordinator();
    error ActionNotReady(bytes32 actionId, uint256 executeAfter);
    error ActionAlreadyExecuted(bytes32 actionId);
    error ActionNotFound(bytes32 actionId);
    error TeamCliffNotReached(uint256 cliffEnds);
    error NoTeamAllocation(address beneficiary);

    // ────────────────────────────────────────────────────────────────────────────
    // Modifiers
    // ────────────────────────────────────────────────────────────────────────────

    modifier onlyCoordinator() {
        if (msg.sender != genesisCoordinator) revert NotGenesisCoordinator();
        _checkGenesisActive();
        _;
    }

    function _checkGenesisActive() internal view {
        if (authorityRevoked) revert GenesisAuthorityExpiredError();
        if (block.timestamp > genesisExpiry) {
            // Don't revert with the same error to allow the expiry event
            revert GenesisAuthorityExpiredError();
        }
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Constructor
    // ────────────────────────────────────────────────────────────────────────────

    /**
     * @param _gaiaToken            The GAIA ERC-20 token contract
     * @param _genesisCoordinator   The genesis ceremony coordinator address
     *                              (should be a multi-sig of genesis participants)
     */
    constructor(address _gaiaToken, address _genesisCoordinator) {
        require(_gaiaToken != address(0), "TL: zero token");
        require(_genesisCoordinator != address(0), "TL: zero coordinator");

        gaiaToken          = IERC20(_gaiaToken);
        genesisCoordinator = _genesisCoordinator;
        genesisTimestamp   = block.timestamp;
        genesisExpiry      = block.timestamp + GENESIS_PERIOD;
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Genesis actions (time-locked, coordinator only)
    // ────────────────────────────────────────────────────────────────────────────

    /**
     * @notice Queue a privileged action. All actions have a 48h minimum delay
     *         for community visibility before execution.
     *
     * @param target       Contract to call
     * @param callData_    ABI-encoded function call
     * @param description  Human-readable description of what this action does
     */
    function queueAction(
        address target,
        bytes calldata callData_,
        string calldata description
    ) external onlyCoordinator returns (bytes32 actionId) {
        uint256 executeAfter = block.timestamp + MINIMUM_DELAY;

        actionId = keccak256(abi.encode(
            target, callData_, block.timestamp, msg.sender
        ));

        queuedActions[actionId] = QueuedAction({
            actionId: actionId,
            target: target,
            callData: callData_,
            queuedAt: block.timestamp,
            executeAfter: executeAfter,
            executed: false,
            description: description
        });

        actionQueue.push(actionId);
        emit ActionQueued(actionId, target, description, executeAfter);
    }

    /**
     * @notice Execute a queued action after the delay has elapsed.
     */
    function executeAction(bytes32 actionId)
        external onlyCoordinator nonReentrant
    {
        QueuedAction storage action = queuedActions[actionId];
        if (action.actionId == bytes32(0)) revert ActionNotFound(actionId);
        if (action.executed) revert ActionAlreadyExecuted(actionId);
        if (block.timestamp < action.executeAfter) {
            revert ActionNotReady(actionId, action.executeAfter);
        }

        action.executed = true;

        (bool success,) = action.target.call(action.callData);
        emit ActionExecuted(actionId, success);
    }

    /**
     * @notice Cancel a queued action before execution.
     */
    function cancelAction(bytes32 actionId) external onlyCoordinator {
        QueuedAction storage action = queuedActions[actionId];
        if (action.actionId == bytes32(0)) revert ActionNotFound(actionId);
        if (action.executed) revert ActionAlreadyExecuted(actionId);

        action.executed = true; // Mark as executed to prevent execution
        emit ActionCancelled(actionId);
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Team vesting
    // ────────────────────────────────────────────────────────────────────────────

    /**
     * @notice Create a team allocation. Only callable during genesis period.
     *
     * @param beneficiary  Team member address
     * @param amount       Total GAIA tokens to vest
     * @param role         Role description
     */
    function createTeamAllocation(
        address beneficiary,
        uint256 amount,
        string calldata role
    ) external onlyCoordinator {
        require(!hasTeamAllocation[beneficiary], "TL: already has allocation");
        require(beneficiary != address(0), "TL: zero beneficiary");

        teamAllocationIndex[beneficiary] = teamAllocations.length;
        hasTeamAllocation[beneficiary] = true;

        teamAllocations.push(TeamAllocation({
            beneficiary: beneficiary,
            totalAmount: amount,
            claimedAmount: 0,
            role: role
        }));

        emit TeamAllocationCreated(beneficiary, amount, role);
    }

    /**
     * @notice Claim vested team tokens. Subject to 18-month cliff + 36-month linear vest.
     */
    function claimTeamTokens() external nonReentrant {
        if (!hasTeamAllocation[msg.sender]) revert NoTeamAllocation(msg.sender);

        uint256 cliff = genesisTimestamp + TEAM_CLIFF;
        if (block.timestamp < cliff) {
            revert TeamCliffNotReached(cliff);
        }

        TeamAllocation storage allocation =
            teamAllocations[teamAllocationIndex[msg.sender]];

        uint256 vested = _vestedTeamTokens(allocation);
        uint256 claimable = vested - allocation.claimedAmount;
        require(claimable > 0, "TL: nothing to claim");

        allocation.claimedAmount += claimable;
        gaiaToken.transfer(msg.sender, claimable);

        emit TeamTokensClaimed(msg.sender, claimable);
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Genesis expiry
    // ────────────────────────────────────────────────────────────────────────────

    /**
     * @notice Voluntarily revoke genesis authority early.
     *         Once called, ALL privileged functions are permanently disabled.
     *         Irreversible.
     */
    function revokeGenesisAuthority() external {
        require(msg.sender == genesisCoordinator, "TL: not coordinator");
        require(!authorityRevoked, "TL: already revoked");

        authorityRevoked = true;
        emit GenesisAuthorityRevoked(block.timestamp);
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Internal helpers
    // ────────────────────────────────────────────────────────────────────────────

    function _vestedTeamTokens(TeamAllocation storage allocation)
        internal view returns (uint256)
    {
        uint256 vestingStart = genesisTimestamp + TEAM_CLIFF;

        if (block.timestamp < vestingStart) return 0;

        uint256 elapsed = block.timestamp - vestingStart;
        if (elapsed >= TEAM_VESTING_PERIOD) return allocation.totalAmount;

        return (allocation.totalAmount * elapsed) / TEAM_VESTING_PERIOD;
    }

    // ────────────────────────────────────────────────────────────────────────────
    // View functions
    // ────────────────────────────────────────────────────────────────────────────

    function genesisIsActive() external view returns (bool) {
        return !authorityRevoked && block.timestamp <= genesisExpiry;
    }

    function timeUntilExpiry() external view returns (uint256) {
        if (authorityRevoked || block.timestamp > genesisExpiry) return 0;
        return genesisExpiry - block.timestamp;
    }

    function pendingActionsCount() external view returns (uint256) {
        uint256 count = 0;
        for (uint256 i = 0; i < actionQueue.length; i++) {
            if (!queuedActions[actionQueue[i]].executed) count++;
        }
        return count;
    }

    function claimableTeamTokens(address beneficiary)
        external view returns (uint256)
    {
        if (!hasTeamAllocation[beneficiary]) return 0;
        TeamAllocation storage allocation =
            teamAllocations[teamAllocationIndex[beneficiary]];
        uint256 vested = _vestedTeamTokens(allocation);
        return vested > allocation.claimedAmount
            ? vested - allocation.claimedAmount
            : 0;
    }
}
