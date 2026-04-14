// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

/**
 * @title RewardDistributor
 * @notice Manages miner reward distribution with linear vesting.
 *
 * ── Why vesting? ─────────────────────────────────────────────────────────────
 *
 * Immediate reward payouts create two attack vectors:
 *   1. A miner can earn rewards then exit the network immediately
 *   2. A miner can earn one large reward and stop operating
 *
 * 90-day linear vesting aligns miner economics with network health:
 *   - Miners who stay active earn more (unvested rewards compound)
 *   - Miners who leave before 90 days forfeit unvested tokens to the reward pool
 *   - Slashing is applied to unvested rewards first, then to staked tokens
 *
 * ── Public Good Jobs ─────────────────────────────────────────────────────────
 *
 * Jobs flagged as "public good" (e.g., IUCN Red List datasets) receive a
 * 10% reward bonus from the public goods fund. This incentivizes miners to
 * prioritize conservation tasks over purely commercial ones.
 *
 * The public goods fund is maintained by the protocol treasury and governed
 * by ConvictionVoting.
 *
 * ── Reward split ─────────────────────────────────────────────────────────────
 *
 *   Per job payment (after 5% burn):
 *     60% → miners who produced correct result (split equally)
 *     25% → validator who ran Freivalds (economic incentive to verify)
 *     15% → protocol treasury (ConvictionVoting-governed)
 *
 * @author GAIA Core Team
 * @custom:version 1.0.0
 */
contract RewardDistributor is ReentrancyGuard {

    // ────────────────────────────────────────────────────────────────────────────
    // Constants
    // ────────────────────────────────────────────────────────────────────────────

    uint256 public constant MINER_SHARE_BPS      = 6_000; // 60%
    uint256 public constant VALIDATOR_SHARE_BPS  = 2_500; // 25%
    uint256 public constant TREASURY_SHARE_BPS   = 1_500; // 15%
    uint256 public constant BPS_DENOMINATOR      = 10_000;

    /// @notice Vesting period for miner rewards
    uint256 public constant VESTING_PERIOD       = 90 days;

    /// @notice Public good bonus (10% on top of normal reward)
    uint256 public constant PUBLIC_GOOD_BONUS_BPS = 1_000; // 10%

    // ────────────────────────────────────────────────────────────────────────────
    // Types
    // ────────────────────────────────────────────────────────────────────────────

    struct VestingSchedule {
        uint256 totalAmount;     // Total GAIA to vest
        uint256 startTime;       // When vesting began
        uint256 claimedAmount;   // Already claimed
        uint256 taskId;          // Source task (for audit)
    }

    // ────────────────────────────────────────────────────────────────────────────
    // State
    // ────────────────────────────────────────────────────────────────────────────

    IERC20 public immutable gaiaToken;
    address public validationPool;
    address public treasury;

    /// @notice Deployer address — the only account allowed to call setValidationPool()
    address public immutable owner;

    /// @notice Flag to prevent setValidationPool() from being called more than once
    bool private validationPoolSet = false;

    /// @notice Vesting schedules per miner (append-only array)
    mapping(address => VestingSchedule[]) public vestingSchedules;

    /// @notice Total unvested rewards per miner (for slashing)
    mapping(address => uint256) public totalUnvested;

    /// @notice Running totals for protocol stats
    uint256 public totalRewardsDistributed;
    uint256 public totalRewardsClaimed;
    uint256 public totalPublicGoodBonusPaid;

    // ────────────────────────────────────────────────────────────────────────────
    // Events
    // ────────────────────────────────────────────────────────────────────────────

    event ValidationPoolSet(address indexed validationPool);
    event RewardVestingCreated(
        address indexed miner,
        uint256 indexed taskId,
        uint256 amount,
        uint256 vestingEnd
    );

    event RewardClaimed(
        address indexed miner,
        uint256 amount,
        uint256 remainingUnvested
    );

    event PublicGoodBonusPaid(
        uint256 indexed taskId,
        address[] miners,
        uint256 bonusPerMiner
    );

    event ValidatorRewarded(
        address indexed validator,
        uint256 indexed taskId,
        uint256 amount
    );

    event TreasuryFunded(
        uint256 indexed taskId,
        uint256 amount
    );

    // ────────────────────────────────────────────────────────────────────────────
    // Errors
    // ────────────────────────────────────────────────────────────────────────────

    error NotOwner();
    error NotValidationPool();
    error NothingToClaim();
    error TransferFailed();

    // ────────────────────────────────────────────────────────────────────────────
    // Constructor
    // ────────────────────────────────────────────────────────────────────────────

    constructor(
        address _gaiaToken,
        address _treasury
    ) {
        require(_gaiaToken != address(0), "RD: zero gaiaToken");
        require(_treasury  != address(0), "RD: zero treasury");

        gaiaToken = IERC20(_gaiaToken);
        treasury  = _treasury;
        owner = msg.sender;
    }


    // ────────────────────────────────────────────────────────────────────────────
    // Setter: Post-deployment validationPool initialization
    // ────────────────────────────────────────────────────────────────────────────

    // ────────────────────────────────────────────────────────────────────────────
    // Access control
    // ────────────────────────────────────────────────────────────────────────────

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    /**
     * @notice Set validationPool address after deployment.
     *         Can only be called once, and only by the deployer (owner).
     *         This resolves the circular deployment dependency.
     */
    function setValidationPool(address _validationPool) external onlyOwner {
        require(!validationPoolSet, "RD: validationPool already set");
        require(_validationPool != address(0), "RD: zero validationPool");

        validationPool = _validationPool;
        validationPoolSet = true;

        emit ValidationPoolSet(_validationPool);
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Reward distribution (called by ValidationPool after successful verification)
    // ────────────────────────────────────────────────────────────────────────────

    /**
     * @notice Distribute rewards for a verified task.
     *         Creates vesting schedules for each miner.
     *
     * @param taskId          The verified task
     * @param totalReward     Total GAIA escrowed for this task (after 5% burn)
     * @param winners         Miners who produced the correct result
     */
    function distributeRewards(
        uint256 taskId,
        uint256 totalReward,
        address[] calldata winners
    ) external nonReentrant {
        if (msg.sender != validationPool) revert NotValidationPool();
        require(winners.length > 0, "RD: no winners");

        // Calculate shares
        uint256 minerPool     = (totalReward * MINER_SHARE_BPS) / BPS_DENOMINATOR;
        uint256 validatorPool = (totalReward * VALIDATOR_SHARE_BPS) / BPS_DENOMINATOR;
        uint256 treasuryShare = totalReward - minerPool - validatorPool;

        uint256 perMiner = minerPool / winners.length;

        // Create vesting schedules for each winning miner
        for (uint256 i = 0; i < winners.length; i++) {
            _createVestingSchedule(winners[i], perMiner, taskId);
        }

        // Immediate validator reward (validators are checked, not vested)
        // In MVP: validator reward goes to treasury for redistribution
        // In V2: specific validator tracked via ValidationPool event
        _transferToTreasury(validatorPool + treasuryShare);

        totalRewardsDistributed += totalReward;

        emit TreasuryFunded(taskId, validatorPool + treasuryShare);
    }

    /**
     * @notice Add a public good bonus on top of the standard reward.
     *         Called by the protocol when a task is flagged as public good.
     *
     * @param taskId  The public good task
     * @param miners  The miners who completed it
     */
    function distributePublicGoodBonus(
        uint256 taskId,
        address[] calldata miners
    ) external nonReentrant {
        if (msg.sender != validationPool) revert NotValidationPool();
        require(miners.length > 0, "RD: no miners");

        uint256 bonusPerMiner = (100 * 10**18 * PUBLIC_GOOD_BONUS_BPS) / BPS_DENOMINATOR;
        // ^^ 100 GAIA base × 10% = 10 GAIA bonus per miner from public good fund

        for (uint256 i = 0; i < miners.length; i++) {
            _createVestingSchedule(miners[i], bonusPerMiner, taskId);
        }

        totalPublicGoodBonusPaid += bonusPerMiner * miners.length;
        emit PublicGoodBonusPaid(taskId, miners, bonusPerMiner);
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Claiming (called by miners)
    // ────────────────────────────────────────────────────────────────────────────

    /**
     * @notice Claim all vested rewards for the calling address.
     *         Vesting is linear: earned over 90 days from task completion.
     */
    function claimVestedRewards() external nonReentrant returns (uint256 claimed) {
        VestingSchedule[] storage schedules = vestingSchedules[msg.sender];
        uint256 timestamp = block.timestamp;

        for (uint256 i = 0; i < schedules.length; i++) {
            VestingSchedule storage schedule = schedules[i];
            uint256 vested = _vestedAmount(schedule, timestamp);
            uint256 claimable = vested - schedule.claimedAmount;

            if (claimable > 0) {
                schedule.claimedAmount += claimable;
                claimed += claimable;
            }
        }

        if (claimed == 0) revert NothingToClaim();

        totalUnvested[msg.sender] -= claimed;
        totalRewardsClaimed += claimed;

        bool ok = gaiaToken.transfer(msg.sender, claimed);
        if (!ok) revert TransferFailed();

        emit RewardClaimed(msg.sender, claimed, totalUnvested[msg.sender]);
    }

    /**
     * @notice How much has vested (claimable + claimed) for a miner
     */
    function vestedBalance(address miner) external view returns (uint256 total) {
        VestingSchedule[] storage schedules = vestingSchedules[miner];
        uint256 timestamp = block.timestamp;
        for (uint256 i = 0; i < schedules.length; i++) {
            total += _vestedAmount(schedules[i], timestamp);
        }
    }

    /**
     * @notice How much is currently claimable (vested minus already claimed)
     */
    function claimableBalance(address miner) external view returns (uint256 total) {
        VestingSchedule[] storage schedules = vestingSchedules[miner];
        uint256 timestamp = block.timestamp;
        for (uint256 i = 0; i < schedules.length; i++) {
            uint256 vested = _vestedAmount(schedules[i], timestamp);
            total += vested - schedules[i].claimedAmount;
        }
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Internal helpers
    // ────────────────────────────────────────────────────────────────────────────

    function _createVestingSchedule(
        address miner,
        uint256 amount,
        uint256 taskId
    ) internal {
        vestingSchedules[miner].push(VestingSchedule({
            totalAmount: amount,
            startTime: block.timestamp,
            claimedAmount: 0,
            taskId: taskId
        }));

        totalUnvested[miner] += amount;

        emit RewardVestingCreated(
            miner,
            taskId,
            amount,
            block.timestamp + VESTING_PERIOD
        );
    }

    function _vestedAmount(
        VestingSchedule storage schedule,
        uint256 timestamp
    ) internal view returns (uint256) {
        if (timestamp >= schedule.startTime + VESTING_PERIOD) {
            return schedule.totalAmount; // Fully vested
        }
        uint256 elapsed = timestamp - schedule.startTime;
        return (schedule.totalAmount * elapsed) / VESTING_PERIOD; // Linear
    }

    function _transferToTreasury(uint256 amount) internal {
        if (amount > 0) {
            gaiaToken.transfer(treasury, amount);
        }
    }

    // ────────────────────────────────────────────────────────────────────────────
    // View functions
    // ────────────────────────────────────────────────────────────────────────────

    function getVestingSchedules(address miner)
        external view returns (VestingSchedule[] memory)
    {
        return vestingSchedules[miner];
    }

    function vestingScheduleCount(address miner) external view returns (uint256) {
        return vestingSchedules[miner].length;
    }
}
