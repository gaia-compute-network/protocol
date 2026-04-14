// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "./FrozenOracle.sol";

/**
 * @title TaskRegistry
 * @notice Central registry for all GAIA compute jobs.
 *
 * ── Lifecycle of a GAIA compute job ─────────────────────────────────────────
 *
 *   PENDING ──► ASSIGNED ──► COMPUTING ──► VALIDATING ──► VERIFIED
 *                                                    └──► FAILED
 *                                                    └──► DISPUTED
 *
 *   1. Requester calls submitTask() with reward in GAIA tokens
 *      → 5% burned immediately (burn-and-mint equilibrium)
 *      → 95% escrowed in this contract
 *
 *   2. Protocol assigns the task to N miners (default: 3)
 *      → Task enters ASSIGNED state
 *
 *   3. Miners compute independently and call submitResult()
 *      → Each miner submits: (resultHash, resultFingerprint, commitment)
 *      → Commitment prevents result-copying (see freivalds.py)
 *
 *   4. After all miners submit, ValidationPool.verifyQuorum() is called
 *      → Freivalds algorithm checks result correctness
 *      → Quorum (≥2/3) determines consensus
 *      → Dissenters are slashed
 *
 *   5. On success: RewardDistributor pays miners
 *      On failure: Requester refunded (minus burn), miners slashed
 *
 * ── Privacy constraints ──────────────────────────────────────────────────────
 *
 *   Raw input data (images, GPS coordinates) is NEVER stored on-chain.
 *   The on-chain record contains only:
 *     - taskHash: SHA-256 of the quantized input matrices
 *     - jobTypeId: keccak256 of the job type string
 *     - rewardAmount: GAIA tokens escrowed
 *     - resultFingerprint: SHA-256(jobId + result) — consensus proof
 *
 *   Actual input data lives off-chain (IPFS or encrypted requester store).
 *   Miners receive encoded inputs via the off-chain job dispatch protocol.
 *
 * @author GAIA Core Team
 * @custom:version 1.0.0
 */
contract TaskRegistry is ReentrancyGuard {

    // ────────────────────────────────────────────────────────────────────────────
    // Types
    // ────────────────────────────────────────────────────────────────────────────

    enum TaskStatus {
        PENDING,     // Submitted, not yet assigned
        ASSIGNED,    // Miners assigned, awaiting computation
        COMPUTING,   // Miners acknowledged the task
        VALIDATING,  // Results submitted, Freivalds running
        VERIFIED,    // Consensus reached, result correct
        FAILED,      // Verification failed or timeout
        DISPUTED     // Potential collusion detected, under review
    }

    struct Task {
        uint256 taskId;
        address requester;
        bytes32 taskHash;           // SHA-256 of quantized input matrices
        bytes32 jobTypeId;          // FrozenOracle-validated job type
        uint256 rewardAmount;       // GAIA tokens (after 5% burn)
        uint256 submittedAt;
        uint256 assignedAt;
        uint256 completedAt;
        uint256 verifiedAt;
        TaskStatus status;
        address[] assignedMiners;
        bytes32 agreedFingerprint;  // Result fingerprint after consensus
        uint256 requiredMiners;     // Default: 3 (configurable per task tier)
        string metadataCountry;     // ISO-3166 country code (coarsened, public)
        bytes32 metadataEncrypted;  // Encrypted detail hash (private, requester key)
    }

    struct MinerSubmission {
        address miner;
        bytes32 resultHash;         // Full SHA-256(result) — for audit
        bytes32 commitment;         // SHA-256(jobId+minerId+timestamp+result) — anti-copy
        bytes32 resultFingerprint;  // SHA-256(jobId+result) — consensus
        uint256 submittedAt;
        bool slashed;
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Constants
    // ────────────────────────────────────────────────────────────────────────────

    uint256 public constant BURN_RATE_BPS        = 500;   // 5% burned on submission
    uint256 public constant MIN_REWARD           = 10 * 10**18; // 10 GAIA minimum
    uint256 public constant DEFAULT_MINER_COUNT  = 3;
    uint256 public constant TASK_TIMEOUT         = 1 hours;
    uint256 public constant BPS_DENOMINATOR      = 10_000;

    // ────────────────────────────────────────────────────────────────────────────
    // State
    // ────────────────────────────────────────────────────────────────────────────

    IERC20 public immutable gaiaToken;
    FrozenOracle public immutable oracle;
    address public immutable validationPool;
    address public immutable rewardDistributor;

    uint256 public taskCounter;
    mapping(uint256 => Task) public tasks;
    mapping(uint256 => MinerSubmission[]) public submissions;
    mapping(uint256 => mapping(address => bool)) public hasSubmitted;

    // Global stats
    uint256 public totalTasksSubmitted;
    uint256 public totalTasksVerified;
    uint256 public totalRewardsPaid;
    uint256 public totalTokensBurned;

    // ────────────────────────────────────────────────────────────────────────────
    // Events
    // ────────────────────────────────────────────────────────────────────────────

    event TaskSubmitted(
        uint256 indexed taskId,
        address indexed requester,
        bytes32 jobTypeId,
        uint256 rewardEscrowed,
        uint256 amountBurned
    );

    event MinersAssigned(
        uint256 indexed taskId,
        address[] miners
    );

    event ResultSubmitted(
        uint256 indexed taskId,
        address indexed miner,
        bytes32 resultFingerprint
    );

    event TaskVerified(
        uint256 indexed taskId,
        bytes32 agreedFingerprint,
        address[] rewardedMiners,
        address[] slashedMiners
    );

    event TaskFailed(
        uint256 indexed taskId,
        string reason
    );

    event TaskTimedOut(
        uint256 indexed taskId
    );

    // ────────────────────────────────────────────────────────────────────────────
    // Errors
    // ────────────────────────────────────────────────────────────────────────────

    error InsufficientReward(uint256 provided, uint256 minimum);
    error JobTypeNotApproved(bytes32 jobTypeId);
    error TaskNotFound(uint256 taskId);
    error TaskNotInCorrectState(uint256 taskId, TaskStatus current, TaskStatus required);
    error NotAssignedMiner(uint256 taskId, address miner);
    error AlreadySubmitted(uint256 taskId, address miner);
    error NotValidationPool();
    error NotRewardDistributor();
    error TaskTimedOutError(uint256 taskId);
    error InvalidCommitment();

    // ────────────────────────────────────────────────────────────────────────────
    // Constructor
    // ────────────────────────────────────────────────────────────────────────────

    constructor(
        address _gaiaToken,
        address _oracle,
        address _validationPool,
        address _rewardDistributor
    ) {
        require(_gaiaToken != address(0), "TR: zero gaiaToken");
        require(_oracle != address(0), "TR: zero oracle");
        require(_validationPool != address(0), "TR: zero validationPool");
        require(_rewardDistributor != address(0), "TR: zero rewardDistributor");

        gaiaToken      = IERC20(_gaiaToken);
        oracle         = FrozenOracle(_oracle);
        validationPool = _validationPool;
        rewardDistributor = _rewardDistributor;
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Task submission
    // ────────────────────────────────────────────────────────────────────────────

    /**
     * @notice Submit a compute job to the GAIA network.
     *
     * @param taskHash            SHA-256 of the quantized input matrices (bytes32)
     * @param jobTypeId_          FrozenOracle job type (keccak256 of type string)
     * @param rewardAmount        GAIA tokens to pay miners (5% will be burned)
     * @param metadataCountry     ISO-3166 alpha-3 country code ("KGZ", "KEN", etc.)
     * @param metadataEncrypted   Encrypted detail hash (for requester-key audit only)
     * @param requiredMiners      Number of miners (3 for standard, 5 for critical jobs)
     *
     * @return taskId  The assigned task ID
     */
    function submitTask(
        bytes32 taskHash,
        bytes32 jobTypeId_,
        uint256 rewardAmount,
        string calldata metadataCountry,
        bytes32 metadataEncrypted,
        uint256 requiredMiners
    ) external nonReentrant returns (uint256 taskId) {
        // Validate reward
        if (rewardAmount < MIN_REWARD) {
            revert InsufficientReward(rewardAmount, MIN_REWARD);
        }

        // Validate job type against FrozenOracle
        oracle.requireApproved(jobTypeId_);

        // Pull tokens from requester
        gaiaToken.transferFrom(msg.sender, address(this), rewardAmount);

        // Burn 5% immediately (burn-and-mint equilibrium)
        uint256 burnAmount = (rewardAmount * BURN_RATE_BPS) / BPS_DENOMINATOR;
        uint256 escrowed   = rewardAmount - burnAmount;

        // Transfer burn portion to zero address via token contract
        // (GAIAToken.burn called via allowance pattern)
        gaiaToken.transfer(address(0xdead), burnAmount); // symbolic burn address

        totalTokensBurned += burnAmount;

        // Create task record
        taskId = ++taskCounter;
        uint256 miners = requiredMiners >= 3 ? requiredMiners : DEFAULT_MINER_COUNT;

        tasks[taskId] = Task({
            taskId: taskId,
            requester: msg.sender,
            taskHash: taskHash,
            jobTypeId: jobTypeId_,
            rewardAmount: escrowed,
            submittedAt: block.timestamp,
            assignedAt: 0,
            completedAt: 0,
            verifiedAt: 0,
            status: TaskStatus.PENDING,
            assignedMiners: new address[](0),
            agreedFingerprint: bytes32(0),
            requiredMiners: miners,
            metadataCountry: metadataCountry,
            metadataEncrypted: metadataEncrypted
        });

        totalTasksSubmitted++;

        emit TaskSubmitted(taskId, msg.sender, jobTypeId_, escrowed, burnAmount);
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Miner assignment (called by the off-chain dispatcher / protocol node)
    // ────────────────────────────────────────────────────────────────────────────

    /**
     * @notice Assign miners to a pending task.
     *         In production: called by the on-chain scheduler or a DAO-governed
     *         dispatcher. In MVP: called by the ValidationPool contract.
     */
    function assignMiners(
        uint256 taskId,
        address[] calldata miners
    ) external {
        // Only the ValidationPool can assign miners
        if (msg.sender != validationPool) revert NotValidationPool();

        Task storage task = _requireTask(taskId);
        _requireStatus(task, TaskStatus.PENDING);
        require(miners.length == task.requiredMiners, "TR: wrong miner count");

        task.assignedMiners = miners;
        task.assignedAt = block.timestamp;
        task.status = TaskStatus.ASSIGNED;

        emit MinersAssigned(taskId, miners);
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Result submission (called by miners)
    // ────────────────────────────────────────────────────────────────────────────

    /**
     * @notice Submit a computation result. Miners call this after completing
     *         their assigned task.
     *
     * @param taskId             The task being completed
     * @param resultHash         SHA-256(result matrix bytes) — full hash for audit
     * @param commitment         SHA-256(jobId+minerId+timestamp+result) — anti-copy
     * @param resultFingerprint  SHA-256(jobId+result) — consensus fingerprint
     */
    function submitResult(
        uint256 taskId,
        bytes32 resultHash,
        bytes32 commitment,
        bytes32 resultFingerprint
    ) external nonReentrant {
        Task storage task = _requireTask(taskId);

        // Status can be ASSIGNED or COMPUTING
        require(
            task.status == TaskStatus.ASSIGNED ||
            task.status == TaskStatus.COMPUTING,
            "TR: task not in computing state"
        );

        // Check timeout
        if (block.timestamp > task.assignedAt + TASK_TIMEOUT) {
            task.status = TaskStatus.FAILED;
            emit TaskTimedOut(taskId);
            revert TaskTimedOutError(taskId);
        }

        // Verify this miner is assigned
        bool isAssigned = false;
        for (uint256 i = 0; i < task.assignedMiners.length; i++) {
            if (task.assignedMiners[i] == msg.sender) {
                isAssigned = true;
                break;
            }
        }
        if (!isAssigned) revert NotAssignedMiner(taskId, msg.sender);
        if (hasSubmitted[taskId][msg.sender]) revert AlreadySubmitted(taskId, msg.sender);

        // Record submission
        submissions[taskId].push(MinerSubmission({
            miner: msg.sender,
            resultHash: resultHash,
            commitment: commitment,
            resultFingerprint: resultFingerprint,
            submittedAt: block.timestamp,
            slashed: false
        }));

        hasSubmitted[taskId][msg.sender] = true;
        task.status = TaskStatus.COMPUTING;

        emit ResultSubmitted(taskId, msg.sender, resultFingerprint);

        // If all miners have submitted, trigger validation
        if (submissions[taskId].length == task.assignedMiners.length) {
            task.status = TaskStatus.VALIDATING;
            task.completedAt = block.timestamp;
        }
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Finalization (called by ValidationPool after Freivalds check)
    // ────────────────────────────────────────────────────────────────────────────

    /**
     * @notice Mark a task as verified and record the agreed result fingerprint.
     *         Called by ValidationPool after successful Freivalds verification.
     *
     * @param taskId              The verified task
     * @param agreedFingerprint   The consensus result fingerprint
     * @param slashedMiners       Addresses of miners whose results deviated
     */
    function finalizeTaskVerified(
        uint256 taskId,
        bytes32 agreedFingerprint,
        address[] calldata slashedMiners
    ) external {
        if (msg.sender != validationPool) revert NotValidationPool();

        Task storage task = _requireTask(taskId);
        _requireStatus(task, TaskStatus.VALIDATING);

        task.agreedFingerprint = agreedFingerprint;
        task.verifiedAt = block.timestamp;
        task.status = TaskStatus.VERIFIED;

        // Mark slashed submissions
        for (uint256 i = 0; i < slashedMiners.length; i++) {
            for (uint256 j = 0; j < submissions[taskId].length; j++) {
                if (submissions[taskId][j].miner == slashedMiners[i]) {
                    submissions[taskId][j].slashed = true;
                }
            }
        }

        totalTasksVerified++;

        // Determine rewarded miners (all assigned minus slashed)
        address[] memory rewarded = new address[](
            task.assignedMiners.length - slashedMiners.length
        );
        uint256 idx = 0;
        for (uint256 i = 0; i < task.assignedMiners.length; i++) {
            bool isSlashed = false;
            for (uint256 j = 0; j < slashedMiners.length; j++) {
                if (task.assignedMiners[i] == slashedMiners[j]) {
                    isSlashed = true;
                    break;
                }
            }
            if (!isSlashed) {
                rewarded[idx++] = task.assignedMiners[i];
            }
        }

        emit TaskVerified(taskId, agreedFingerprint, rewarded, slashedMiners);
    }

    /**
     * @notice Mark a task as failed. Requester gets refund, miners may be slashed.
     */
    function finalizeTaskFailed(
        uint256 taskId,
        string calldata reason
    ) external {
        if (msg.sender != validationPool) revert NotValidationPool();

        Task storage task = _requireTask(taskId);
        require(
            task.status == TaskStatus.VALIDATING ||
            task.status == TaskStatus.COMPUTING ||
            task.status == TaskStatus.ASSIGNED,
            "TR: cannot fail task in this state"
        );

        task.status = TaskStatus.FAILED;
        emit TaskFailed(taskId, reason);
    }

    // ────────────────────────────────────────────────────────────────────────────
    // View functions
    // ────────────────────────────────────────────────────────────────────────────

    function getTask(uint256 taskId) external view returns (Task memory) {
        return tasks[taskId];
    }

    function getSubmissions(uint256 taskId)
        external view returns (MinerSubmission[] memory)
    {
        return submissions[taskId];
    }

    function isReadyForValidation(uint256 taskId) external view returns (bool) {
        Task storage task = tasks[taskId];
        return task.status == TaskStatus.VALIDATING;
    }

    function getTaskReward(uint256 taskId) external view returns (uint256) {
        return tasks[taskId].rewardAmount;
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Internal helpers
    // ────────────────────────────────────────────────────────────────────────────

    function _requireTask(uint256 taskId) internal view returns (Task storage) {
        Task storage task = tasks[taskId];
        if (task.taskId == 0) revert TaskNotFound(taskId);
        return task;
    }

    function _requireStatus(Task storage task, TaskStatus required) internal view {
        if (task.status != required) {
            revert TaskNotInCorrectState(task.taskId, task.status, required);
        }
    }
}
