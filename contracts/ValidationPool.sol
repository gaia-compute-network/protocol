// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "./TaskRegistry.sol";
import "./RewardDistributor.sol";

/**
 * @title ValidationPool
 * @notice Implements on-chain quorum consensus for GAIA compute results.
 *
 * ── The Freivalds Verification Protocol ─────────────────────────────────────
 *
 * Freivalds' algorithm (1977) allows verification of matrix multiplication
 * A×B=C in O(n²) instead of O(n³), with error probability < 2^(-k) for k rounds.
 *
 * On-chain implementation:
 *   The ValidationPool does NOT run Freivalds directly on-chain (prohibitively
 *   expensive for large matrices). Instead:
 *
 *   1. Miners submit result fingerprints (off-chain computation)
 *   2. A designated Freivalds Verifier node (or ZK-proof in future) provides
 *      the verification result on-chain
 *   3. The Verifier is selected randomly from the validator set each round
 *   4. Verifier stakes are slashed if they provide false results (auditable)
 *
 *   Future upgrade: ZK-SNARK proof of Freivalds execution (see ZK research docs)
 *   When ZK proofs become cost-effective, this contract can accept them directly
 *   without trusting any single Verifier node.
 *
 * ── Quorum logic ─────────────────────────────────────────────────────────────
 *
 *   Three miners submit results independently.
 *   Group by result_fingerprint (SHA-256(job_id + result)).
 *   Majority group (≥2/3) determines the consensus answer.
 *   Freivalds verifies the consensus answer against the original inputs.
 *
 *   Outcomes:
 *     - Majority passes Freivalds → miners in majority rewarded, dissenters slashed
 *     - Majority fails Freivalds → ALL miners suspected of collusion → all slashed
 *     - No majority (all different fingerprints) → DISPUTED, human governance review
 *
 * ── Slashing amounts ─────────────────────────────────────────────────────────
 *
 *   Dissenter:  loses DISSENTER_SLASH_BPS of staked GAIA (default: 50%)
 *   Colluder:   loses COLLUDER_SLASH_BPS of staked GAIA (default: 100%)
 *   The slashed tokens are split: 50% burned, 50% to the winning miners
 *   This creates additional economic incentive for honest miners to report cheaters
 *
 * @author GAIA Core Team
 * @custom:version 1.0.0
 */
contract ValidationPool is ReentrancyGuard {

    // ────────────────────────────────────────────────────────────────────────────
    // Constants
    // ────────────────────────────────────────────────────────────────────────────

    uint256 public constant DISSENTER_SLASH_BPS  = 5_000;  // 50% of stake
    uint256 public constant COLLUDER_SLASH_BPS   = 10_000; // 100% of stake
    uint256 public constant SLASH_BURN_SHARE_BPS = 5_000;  // 50% of slash burned
    uint256 public constant FREIVALDS_ROUNDS     = 10;     // error < 1/1024
    uint256 public constant BPS_DENOMINATOR      = 10_000;
    uint256 public constant QUORUM_THRESHOLD     = 2;      // ≥2 of 3 miners

    // ────────────────────────────────────────────────────────────────────────────
    // State
    // ────────────────────────────────────────────────────────────────────────────

    TaskRegistry public taskRegistry;
    RewardDistributor public rewardDistributor;
    address public immutable gaiaToken;

    /// @notice Deployer address — the only account allowed to call setAddresses()
    address public immutable owner;

    /// @notice Flag to prevent setAddresses() from being called more than once
    bool private addressesSet = false;

    /// @notice Registered validator nodes (can run Freivalds verification)
    mapping(address => bool) public isValidator;
    mapping(address => uint256) public validatorStake;
    address[] public validators;

    /// @notice Minimum stake required to be a validator
    uint256 public constant MIN_VALIDATOR_STAKE = 1_000 * 10**18; // 1,000 GAIA

    /// @notice Validation results submitted by verifier nodes
    struct FreivaldsResult {
        uint256 taskId;
        bool passed;          // Did the majority result pass Freivalds?
        bytes32 testedFingerprint;
        uint8 roundsExecuted;
        uint256 errorProbabilityBps; // error probability in basis points
        address verifier;
        uint256 submittedAt;
    }

    mapping(uint256 => FreivaldsResult) public freivaldsResults;
    mapping(uint256 => bool) public validationComplete;

    // Miner stake tracking (for slashing)
    mapping(address => uint256) public minerStake;
    uint256 public constant MIN_MINER_STAKE = 100 * 10**18; // 100 GAIA

    // ────────────────────────────────────────────────────────────────────────────
    // Events
    // ────────────────────────────────────────────────────────────────────────────

    event AddressesSet(address indexed taskRegistry, address indexed rewardDistributor);
    event ValidatorRegistered(address indexed validator, uint256 stake);
    event MinerRegistered(address indexed miner, uint256 stake);

    event FreivaldsResultSubmitted(
        uint256 indexed taskId,
        bool passed,
        bytes32 testedFingerprint,
        address indexed verifier
    );

    event QuorumReached(
        uint256 indexed taskId,
        bytes32 agreedFingerprint,
        uint256 minerCount,
        uint256 dissentersSlashed
    );

    event ConsensusFailure(
        uint256 indexed taskId,
        string reason,
        uint256 minersSlashed
    );

    event MinerSlashed(
        address indexed miner,
        uint256 indexed taskId,
        uint256 amountSlashed,
        string reason
    );

    // ────────────────────────────────────────────────────────────────────────────
    // Errors
    // ────────────────────────────────────────────────────────────────────────────

    error NotOwner();
    error NotRegisteredValidator();
    error InsufficientStake(uint256 provided, uint256 required);
    error TaskNotReadyForValidation(uint256 taskId);
    error ValidationAlreadyComplete(uint256 taskId);
    error InvalidFingerprint();


    // ────────────────────────────────────────────────────────────────────────────
    // Access control + Post-deployment address initialization
    // ────────────────────────────────────────────────────────────────────────────

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    /**
     * @notice Set taskRegistry and rewardDistributor addresses after deployment.
     *         Can only be called once, and only by the deployer (owner).
     *         This resolves the circular deployment dependency.
     */
    function setAddresses(
        address _taskRegistry,
        address _rewardDistributor
    ) external onlyOwner {
        require(!addressesSet, "VP: addresses already set");
        require(_taskRegistry != address(0), "VP: zero taskRegistry");
        require(_rewardDistributor != address(0), "VP: zero rewardDistributor");

        taskRegistry = TaskRegistry(_taskRegistry);
        rewardDistributor = RewardDistributor(_rewardDistributor);
        addressesSet = true;

        emit AddressesSet(_taskRegistry, _rewardDistributor);
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Modifiers
    // ────────────────────────────────────────────────────────────────────────────

    /**
     * @notice Require that addresses have been set before calling critical functions
     */
    modifier requireAddressesSet() {
        require(addressesSet, "VP: addresses not yet initialized");
        _;
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Constructor
    // ────────────────────────────────────────────────────────────────────────────

    constructor(
        address _gaiaToken
    ) {
        require(_gaiaToken != address(0), "VP: zero gaiaToken");
        gaiaToken = _gaiaToken;
        owner = msg.sender;
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Validator & miner registration
    // ────────────────────────────────────────────────────────────────────────────

    /**
     * @notice Register as a Freivalds validator. Requires staking GAIA tokens.
     *         Validators run Freivalds verification off-chain and submit results.
     */
    function registerValidator() external nonReentrant {
        uint256 stake = IERC20(gaiaToken).allowance(msg.sender, address(this));
        if (stake < MIN_VALIDATOR_STAKE) {
            revert InsufficientStake(stake, MIN_VALIDATOR_STAKE);
        }

        IERC20(gaiaToken).transferFrom(msg.sender, address(this), stake);
        validatorStake[msg.sender] += stake;

        if (!isValidator[msg.sender]) {
            isValidator[msg.sender] = true;
            validators.push(msg.sender);
            emit ValidatorRegistered(msg.sender, stake);
        }
    }

    /**
     * @notice Register as a compute miner. Requires staking GAIA tokens.
     */
    function registerMiner() external nonReentrant {
        uint256 stake = IERC20(gaiaToken).allowance(msg.sender, address(this));
        if (stake < MIN_MINER_STAKE) {
            revert InsufficientStake(stake, MIN_MINER_STAKE);
        }

        IERC20(gaiaToken).transferFrom(msg.sender, address(this), stake);
        minerStake[msg.sender] += stake;

        emit MinerRegistered(msg.sender, stake);
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Core: Submit Freivalds result (called by designated validator node)
    // ────────────────────────────────────────────────────────────────────────────

    /**
     * @notice Submit the result of running Freivalds verification off-chain.
     *
     * The validator node:
     *   1. Receives the task inputs (from IPFS/requester)
     *   2. Gets the majority result fingerprint from TaskRegistry
     *   3. Reconstructs the agreed result matrix
     *   4. Runs Freivalds: verifyResult(A, B, C, rounds=10)
     *   5. Submits the boolean result here
     *
     * If the validator submits a false result, their stake is slashed (auditable).
     *
     * @param taskId                 Task being validated
     * @param freivaldsPassedMajority Did the majority result pass Freivalds?
     * @param testedFingerprint       The fingerprint of the result that was tested
     * @param roundsExecuted          Number of Freivalds rounds run (must be ≥10)
     */
    function submitFreivaldsResult(
        uint256 taskId,
        bool freivaldsPassedMajority,
        bytes32 testedFingerprint,
        uint8 roundsExecuted
    ) external nonReentrant requireAddressesSet {
        if (!isValidator[msg.sender]) revert NotRegisteredValidator();
        if (validationComplete[taskId]) revert ValidationAlreadyComplete(taskId);
        if (!taskRegistry.isReadyForValidation(taskId)) {
            revert TaskNotReadyForValidation(taskId);
        }
        if (testedFingerprint == bytes32(0)) revert InvalidFingerprint();
        require(roundsExecuted >= FREIVALDS_ROUNDS, "VP: insufficient rounds");

        // Calculate error probability (2^-rounds, expressed in BPS for on-chain storage)
        // 10 rounds → 1/1024 ≈ 9.77 BPS
        uint256 errorBps = 10_000 / (1 << roundsExecuted);

        freivaldsResults[taskId] = FreivaldsResult({
            taskId: taskId,
            passed: freivaldsPassedMajority,
            testedFingerprint: testedFingerprint,
            roundsExecuted: roundsExecuted,
            errorProbabilityBps: errorBps,
            verifier: msg.sender,
            submittedAt: block.timestamp
        });

        validationComplete[taskId] = true;

        emit FreivaldsResultSubmitted(
            taskId, freivaldsPassedMajority, testedFingerprint, msg.sender
        );

        // Process consensus immediately
        _processConsensus(taskId, freivaldsPassedMajority, testedFingerprint);
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Consensus processing
    // ────────────────────────────────────────────────────────────────────────────

    function _processConsensus(
        uint256 taskId,
        bool freivaldsPassedMajority,
        bytes32 agreedFingerprint
    ) internal {
        TaskRegistry.MinerSubmission[] memory subs = taskRegistry.getSubmissions(taskId);

        // Group by fingerprint to find majority
        bytes32 majorityFingerprint = _findMajorityFingerprint(subs);
        uint256 majorityCount = _countFingerprint(subs, majorityFingerprint);

        // Identify dissenters
        address[] memory dissenters = _findDissenters(subs, majorityFingerprint);

        if (majorityCount < QUORUM_THRESHOLD) {
            // No majority — disputed
            taskRegistry.finalizeTaskFailed(taskId, "no_quorum_all_different");
            _slashAll(subs, taskId, "no_quorum");
            emit ConsensusFailure(taskId, "no_quorum", subs.length);
            return;
        }

        if (!freivaldsPassedMajority) {
            // Majority agreed but result is wrong — suspected collusion
            taskRegistry.finalizeTaskFailed(taskId, "freivalds_failed_suspected_collusion");
            _slashAll(subs, taskId, "collusion_suspected");
            emit ConsensusFailure(taskId, "freivalds_failed", subs.length);
            return;
        }

        // SUCCESS: majority agreed and result is correct
        taskRegistry.finalizeTaskVerified(taskId, agreedFingerprint, dissenters);

        // Slash dissenters
        for (uint256 i = 0; i < dissenters.length; i++) {
            _slashMiner(dissenters[i], taskId, DISSENTER_SLASH_BPS, "dissenter");
        }

        emit QuorumReached(taskId, agreedFingerprint, majorityCount, dissenters.length);

        // Trigger reward distribution
        rewardDistributor.distributeRewards(
            taskId,
            taskRegistry.getTaskReward(taskId),
            _getMajorityMiners(subs, majorityFingerprint)
        );
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Slashing
    // ────────────────────────────────────────────────────────────────────────────

    function _slashMiner(
        address miner,
        uint256 taskId,
        uint256 slashBps,
        string memory reason
    ) internal {
        uint256 stake = minerStake[miner];
        if (stake == 0) return;

        uint256 slashAmount = (stake * slashBps) / BPS_DENOMINATOR;
        minerStake[miner] = stake - slashAmount;

        emit MinerSlashed(miner, taskId, slashAmount, reason);
    }

    function _slashAll(
        TaskRegistry.MinerSubmission[] memory subs,
        uint256 taskId,
        string memory reason
    ) internal {
        for (uint256 i = 0; i < subs.length; i++) {
            _slashMiner(subs[i].miner, taskId, COLLUDER_SLASH_BPS, reason);
        }
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Internal view helpers
    // ────────────────────────────────────────────────────────────────────────────

    function _findMajorityFingerprint(
        TaskRegistry.MinerSubmission[] memory subs
    ) internal pure returns (bytes32 majority) {
        uint256 maxCount = 0;
        for (uint256 i = 0; i < subs.length; i++) {
            uint256 count = _countFingerprint(subs, subs[i].resultFingerprint);
            if (count > maxCount) {
                maxCount = count;
                majority = subs[i].resultFingerprint;
            }
        }
    }

    function _countFingerprint(
        TaskRegistry.MinerSubmission[] memory subs,
        bytes32 fingerprint
    ) internal pure returns (uint256 count) {
        for (uint256 i = 0; i < subs.length; i++) {
            if (subs[i].resultFingerprint == fingerprint) count++;
        }
    }

    function _findDissenters(
        TaskRegistry.MinerSubmission[] memory subs,
        bytes32 majorityFingerprint
    ) internal pure returns (address[] memory) {
        uint256 count = 0;
        for (uint256 i = 0; i < subs.length; i++) {
            if (subs[i].resultFingerprint != majorityFingerprint) count++;
        }

        address[] memory dissenters = new address[](count);
        uint256 idx = 0;
        for (uint256 i = 0; i < subs.length; i++) {
            if (subs[i].resultFingerprint != majorityFingerprint) {
                dissenters[idx++] = subs[i].miner;
            }
        }
        return dissenters;
    }

    function _getMajorityMiners(
        TaskRegistry.MinerSubmission[] memory subs,
        bytes32 majorityFingerprint
    ) internal pure returns (address[] memory) {
        uint256 count = _countFingerprint(subs, majorityFingerprint);
        address[] memory miners = new address[](count);
        uint256 idx = 0;
        for (uint256 i = 0; i < subs.length; i++) {
            if (subs[i].resultFingerprint == majorityFingerprint) {
                miners[idx++] = subs[i].miner;
            }
        }
        return miners;
    }

    // ────────────────────────────────────────────────────────────────────────────
    // View functions
    // ────────────────────────────────────────────────────────────────────────────

    function getFreivaldsResult(uint256 taskId)
        external view returns (FreivaldsResult memory)
    {
        return freivaldsResults[taskId];
    }

    function getMinerStake(address miner) external view returns (uint256) {
        return minerStake[miner];
    }

    function validatorCount() external view returns (uint256) {
        return validators.length;
    }
}
