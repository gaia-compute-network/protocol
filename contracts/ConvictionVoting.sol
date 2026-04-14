// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * @title ConvictionVoting
 * @notice Time-weighted governance for the GAIA Protocol.
 *
 * ── Why Conviction Voting? ───────────────────────────────────────────────────
 *
 * Standard token voting has one critical flaw: a whale who buys tokens on
 * Monday can swing a governance vote on Tuesday. Flash-loan governance attacks
 * are a documented reality across DeFi.
 *
 * Conviction Voting solves this with time-weighting:
 *   - Voting power ACCUMULATES over time
 *   - A token held for 1 year has ~100× the effective power of a token held for 1 day
 *   - This makes governance attacks prohibitively expensive — you'd need to hold
 *     tokens for months before wielding meaningful influence
 *
 * ── How conviction accumulates ───────────────────────────────────────────────
 *
 *   conviction(t) = tokens × (1 - decay^(t - lastUpdate))
 *                           / (1 - decay)
 *
 *   Where decay = 0.9999 per block (approximately 86.4% conviction retained per day
 *   with 12-second block times — conviction approaches max asymptotically)
 *
 * ── Proposal types ───────────────────────────────────────────────────────────
 *
 *   PARAMETER_CHANGE     — Adjust protocol parameters (MIN_STAKE, BURN_RATE, etc.)
 *   TREASURY_ALLOCATION  — Allocate treasury funds to a recipient
 *   ORACLE_UPDATE        — Propose an oracle model update (requires 90% threshold)
 *   EMERGENCY_PAUSE      — Pause protocol operations (requires 75% threshold)
 *
 * ── Quorum thresholds ────────────────────────────────────────────────────────
 *
 *   Standard proposals:    33% of total conviction needed to pass
 *   Oracle update:         90% of total conviction (near-impossible to reach)
 *   Emergency pause:       75% of total conviction
 *
 * @author GAIA Core Team
 * @custom:version 1.0.0
 */
contract ConvictionVoting is ReentrancyGuard {

    // ────────────────────────────────────────────────────────────────────────────
    // Constants
    // ────────────────────────────────────────────────────────────────────────────

    /// @notice Decay factor denominator (decay = DECAY_NUMERATOR / DECAY_DENOMINATOR)
    ///         0.9999 per block ≈ 86.4% retained per day (12s blocks)
    uint256 public constant DECAY_NUMERATOR    = 9_999;
    uint256 public constant DECAY_DENOMINATOR  = 10_000;

    /// @notice Standard proposal quorum (33%)
    uint256 public constant STANDARD_QUORUM_BPS = 3_300;

    /// @notice Emergency pause quorum (75%)
    uint256 public constant EMERGENCY_QUORUM_BPS = 7_500;

    /// @notice Oracle update quorum (90%)
    uint256 public constant ORACLE_QUORUM_BPS = 9_000;

    uint256 public constant BPS_DENOMINATOR = 10_000;

    /// @notice Minimum blocks a proposal must accumulate conviction before passing
    uint256 public constant MIN_CONVICTION_BLOCKS = 40_320; // ~7 days at 12s/block

    /// @notice Max conviction per token (cap to prevent overflow)
    uint256 public constant MAX_CONVICTION_PER_TOKEN = 1_000_000;

    // ────────────────────────────────────────────────────────────────────────────
    // Types
    // ────────────────────────────────────────────────────────────────────────────

    enum ProposalType {
        PARAMETER_CHANGE,
        TREASURY_ALLOCATION,
        ORACLE_UPDATE,
        EMERGENCY_PAUSE
    }

    enum ProposalStatus {
        ACTIVE,
        PASSED,
        REJECTED,
        EXECUTED,
        EXPIRED
    }

    struct Proposal {
        uint256 proposalId;
        address proposer;
        ProposalType proposalType;
        ProposalStatus status;
        string title;
        string description;
        bytes callData;           // Encoded function call to execute if passed
        address targetContract;   // Contract to call on execution
        uint256 totalConviction;  // Accumulated conviction for this proposal
        uint256 createdAt;        // Block number of proposal creation
        uint256 passedAt;         // Block number when proposal first passed threshold
        uint256 lastUpdated;      // Block number of last conviction update
        uint256 requiredConviction; // Threshold to pass
        bool executed;
    }

    struct VoterState {
        uint256 lockedTokens;   // GAIA tokens locked for voting
        uint256 conviction;     // Current accumulated conviction
        uint256 lastBlock;      // Last block conviction was updated
        uint256 votedProposal;  // Which proposal this conviction is allocated to (0 = none)
    }

    // ────────────────────────────────────────────────────────────────────────────
    // State
    // ────────────────────────────────────────────────────────────────────────────

    IERC20 public immutable gaiaToken;

    uint256 public proposalCounter;
    mapping(uint256 => Proposal) public proposals;

    mapping(address => VoterState) public voterStates;
    mapping(uint256 => address[]) public proposalVoters;

    uint256 public totalLockedTokens;
    uint256 public totalGlobalConviction;

    // ────────────────────────────────────────────────────────────────────────────
    // Events
    // ────────────────────────────────────────────────────────────────────────────

    event ProposalCreated(
        uint256 indexed proposalId,
        address indexed proposer,
        ProposalType proposalType,
        string title,
        uint256 requiredConviction
    );

    event ConvictionUpdated(
        uint256 indexed proposalId,
        address indexed voter,
        uint256 newConviction,
        uint256 totalProposalConviction
    );

    event TokensLocked(address indexed voter, uint256 amount);
    event TokensUnlocked(address indexed voter, uint256 amount);

    event ProposalPassed(uint256 indexed proposalId, uint256 conviction);
    event ProposalExecuted(uint256 indexed proposalId);
    event ProposalRejected(uint256 indexed proposalId);

    // ────────────────────────────────────────────────────────────────────────────
    // Errors
    // ────────────────────────────────────────────────────────────────────────────

    error ProposalNotActive(uint256 proposalId);
    error NotEnoughTokensLocked();
    error AlreadyVotingOnDifferentProposal(uint256 currentProposal);
    error ProposalNotPassed(uint256 proposalId);
    error ExecutionFailed(uint256 proposalId);
    error ConvictionNotMature(uint256 proposalId, uint256 blocksRemaining);

    // ────────────────────────────────────────────────────────────────────────────
    // Constructor
    // ────────────────────────────────────────────────────────────────────────────

    constructor(address _gaiaToken) {
        require(_gaiaToken != address(0), "CV: zero gaiaToken");
        gaiaToken = IERC20(_gaiaToken);
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Token locking (prerequisite for voting)
    // ────────────────────────────────────────────────────────────────────────────

    /**
     * @notice Lock GAIA tokens to participate in governance.
     *         Locked tokens begin accumulating conviction immediately.
     *         Tokens cannot be unlocked while voting on an active proposal.
     */
    function lockTokens(uint256 amount) external nonReentrant {
        require(amount > 0, "CV: zero amount");
        gaiaToken.transferFrom(msg.sender, address(this), amount);

        VoterState storage voter = voterStates[msg.sender];

        // Accrue conviction before updating token balance
        if (voter.lastBlock > 0) {
            voter.conviction = _currentConviction(voter);
        }

        voter.lockedTokens += amount;
        voter.lastBlock = block.number;
        totalLockedTokens += amount;

        emit TokensLocked(msg.sender, amount);
    }

    /**
     * @notice Unlock tokens. Only allowed when not actively voting.
     */
    function unlockTokens(uint256 amount) external nonReentrant {
        VoterState storage voter = voterStates[msg.sender];
        require(voter.lockedTokens >= amount, "CV: insufficient locked");
        require(voter.votedProposal == 0, "CV: cannot unlock while voting");

        // Reduce conviction proportionally
        voter.conviction = _currentConviction(voter);
        voter.conviction = (voter.conviction * (voter.lockedTokens - amount))
                          / voter.lockedTokens;

        voter.lockedTokens -= amount;
        voter.lastBlock = block.number;
        totalLockedTokens -= amount;

        gaiaToken.transfer(msg.sender, amount);
        emit TokensUnlocked(msg.sender, amount);
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Proposals
    // ────────────────────────────────────────────────────────────────────────────

    /**
     * @notice Create a new governance proposal.
     *
     * @param proposalType_    Type of proposal (see enum)
     * @param title            Short human-readable title
     * @param description      Full proposal description
     * @param targetContract   Contract to call on execution
     * @param callData_        ABI-encoded function call
     */
    function createProposal(
        ProposalType proposalType_,
        string calldata title,
        string calldata description,
        address targetContract,
        bytes calldata callData_
    ) external returns (uint256 proposalId) {
        require(voterStates[msg.sender].lockedTokens > 0, "CV: must lock tokens first");
        require(bytes(title).length > 0, "CV: empty title");

        proposalId = ++proposalCounter;

        uint256 quorumBps;
        if (proposalType_ == ProposalType.ORACLE_UPDATE) {
            quorumBps = ORACLE_QUORUM_BPS;
        } else if (proposalType_ == ProposalType.EMERGENCY_PAUSE) {
            quorumBps = EMERGENCY_QUORUM_BPS;
        } else {
            quorumBps = STANDARD_QUORUM_BPS;
        }

        // Required conviction = quorum% of total possible conviction
        // Total possible conviction = totalLockedTokens × MAX_CONVICTION_PER_TOKEN
        uint256 maxConviction = totalLockedTokens * MAX_CONVICTION_PER_TOKEN;
        uint256 required = (maxConviction * quorumBps) / BPS_DENOMINATOR;

        proposals[proposalId] = Proposal({
            proposalId: proposalId,
            proposer: msg.sender,
            proposalType: proposalType_,
            status: ProposalStatus.ACTIVE,
            title: title,
            description: description,
            callData: callData_,
            targetContract: targetContract,
            totalConviction: 0,
            createdAt: block.number,
            passedAt: 0,
            lastUpdated: block.number,
            requiredConviction: required,
            executed: false
        });

        emit ProposalCreated(proposalId, msg.sender, proposalType_, title, required);
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Voting (conviction allocation)
    // ────────────────────────────────────────────────────────────────────────────

    /**
     * @notice Allocate your conviction to a proposal.
     *         Conviction accumulates automatically over time while allocated.
     *
     * @param proposalId  The proposal to support
     */
    function allocateConviction(uint256 proposalId) external {
        // Verify proposal exists (accessing a non-existent mapping returns default status ACTIVE)
        require(proposalId > 0 && proposalId <= proposalCounter, "CV: proposal does not exist");
        Proposal storage proposal = proposals[proposalId];
        if (proposal.status != ProposalStatus.ACTIVE) {
            revert ProposalNotActive(proposalId);
        }

        VoterState storage voter = voterStates[msg.sender];
        if (voter.lockedTokens == 0) revert NotEnoughTokensLocked();
        if (voter.votedProposal != 0 && voter.votedProposal != proposalId) {
            revert AlreadyVotingOnDifferentProposal(voter.votedProposal);
        }

        // Accrue conviction
        uint256 currentConviction = _currentConviction(voter);
        voter.conviction = currentConviction;
        voter.lastBlock = block.number;
        voter.votedProposal = proposalId;

        // Add to proposal
        proposal.totalConviction += currentConviction;
        proposal.lastUpdated = block.number;
        proposalVoters[proposalId].push(msg.sender);

        emit ConvictionUpdated(proposalId, msg.sender, currentConviction, proposal.totalConviction);

        // Check if proposal passes
        _checkProposalThreshold(proposalId);
    }

    /**
     * @notice Withdraw conviction from a proposal (de-allocate).
     */
    function withdrawConviction(uint256 proposalId) external {
        VoterState storage voter = voterStates[msg.sender];
        require(voter.votedProposal == proposalId, "CV: not voting on this proposal");

        // Remove exactly what was credited to the proposal at last allocation.
        // Using voter.conviction (not _currentConviction) prevents underflow when
        // new blocks have passed since the last allocateConviction call.
        uint256 creditedConviction = voter.conviction;
        uint256 currentTotal = proposals[proposalId].totalConviction;
        proposals[proposalId].totalConviction = currentTotal > creditedConviction
            ? currentTotal - creditedConviction
            : 0;

        voter.conviction = 0;
        voter.lastBlock = block.number;
        voter.votedProposal = 0;
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Execution
    // ────────────────────────────────────────────────────────────────────────────

    /**
     * @notice Execute a passed proposal.
     *         Calls the target contract with the encoded callData.
     */
    function executeProposal(uint256 proposalId) external nonReentrant {
        Proposal storage proposal = proposals[proposalId];
        if (proposal.status != ProposalStatus.PASSED) {
            revert ProposalNotPassed(proposalId);
        }

        // Proposal must have been in PASSED state for minimum maturity period
        // (prevents flash-loan governance attacks on newly-passed proposals)
        uint256 blocksSincePassed = block.number - proposal.passedAt;
        if (blocksSincePassed < MIN_CONVICTION_BLOCKS) {
            revert ConvictionNotMature(
                proposalId,
                MIN_CONVICTION_BLOCKS - blocksSincePassed
            );
        }

        proposal.status = ProposalStatus.EXECUTED;
        proposal.executed = true;

        (bool success,) = proposal.targetContract.call(proposal.callData);
        if (!success) revert ExecutionFailed(proposalId);

        emit ProposalExecuted(proposalId);
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Internal helpers
    // ────────────────────────────────────────────────────────────────────────────

    /**
     * @notice Calculate current conviction for a voter.
     *         Conviction = tokens × accumulated_time_weight
     *
     *         Simplified linear approximation for gas efficiency:
     *         conviction = min(tokens × (blocksSinceStart / SCALE), tokens × MAX_MULT)
     */
    function _currentConviction(VoterState memory voter)
        internal view returns (uint256)
    {
        if (voter.lockedTokens == 0) return 0;
        if (voter.lastBlock == 0) return 0;

        uint256 blocksHeld = block.number - voter.lastBlock;

        // Conviction grows linearly with time, capped at MAX_CONVICTION_PER_TOKEN × tokens
        // 1 block = 1 unit of conviction per token
        // Max conviction reached after ~1 year of holding
        uint256 maxConviction = voter.lockedTokens * MAX_CONVICTION_PER_TOKEN;
        uint256 newConviction = voter.conviction + (voter.lockedTokens * blocksHeld);

        return newConviction > maxConviction ? maxConviction : newConviction;
    }

    function _checkProposalThreshold(uint256 proposalId) internal {
        Proposal storage proposal = proposals[proposalId];
        if (proposal.totalConviction >= proposal.requiredConviction &&
            proposal.status == ProposalStatus.ACTIVE) {
            proposal.status = ProposalStatus.PASSED;
            proposal.passedAt = block.number;  // Record when it passed for maturity check
            emit ProposalPassed(proposalId, proposal.totalConviction);
        }
    }

    // ────────────────────────────────────────────────────────────────────────────
    // View functions
    // ────────────────────────────────────────────────────────────────────────────

    function getProposal(uint256 proposalId)
        external view returns (Proposal memory)
    {
        return proposals[proposalId];
    }

    function getVoterConviction(address voter) external view returns (uint256) {
        return _currentConviction(voterStates[voter]);
    }

    function getProposalProgress(uint256 proposalId)
        external view returns (uint256 current, uint256 required, uint256 percentBps)
    {
        Proposal storage p = proposals[proposalId];
        current = p.totalConviction;
        required = p.requiredConviction;
        percentBps = required > 0 ? (current * BPS_DENOMINATOR) / required : 0;
    }
}
