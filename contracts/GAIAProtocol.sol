// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title GAIAProtocol
 * @notice Deployment orchestrator and system registry for the GAIA Protocol.
 *
 * This contract:
 *   1. Holds references to all GAIA system contracts
 *   2. Provides a single address for external integrations to discover contracts
 *   3. Emits genesis events for on-chain auditability
 *   4. Implements emergency pause (via ConvictionVoting, 75% quorum)
 *
 * ── Deployment order ─────────────────────────────────────────────────────────
 *
 *   1. Deploy GAIAToken(genesisReceiver = TimeLock)
 *   2. Deploy ConvictionVoting(gaiaToken)
 *   3. Deploy FrozenOracle(convictionVoting)
 *   4. Deploy RewardDistributor(gaiaToken, validationPool, treasury)
 *   5. Deploy ValidationPool(taskRegistry, rewardDistributor, gaiaToken)
 *   6. Deploy TaskRegistry(gaiaToken, oracle, validationPool, rewardDistributor)
 *   7. Deploy TimeLock(gaiaToken, genesisCoordinatorMultisig)
 *   8. Deploy GAIAProtocol(all addresses above)
 *   9. Call oracle.initializeOracle(modelHash, modelCID)
 *  10. Genesis Ceremony: distribute initial token allocations via TimeLock
 *
 * After step 10 completes and the 18-month genesis period expires,
 * the protocol is fully autonomous.
 *
 * @author GAIA Core Team
 * @custom:version 1.0.0
 */
contract GAIAProtocol {

    // ────────────────────────────────────────────────────────────────────────────
    // Protocol version
    // ────────────────────────────────────────────────────────────────────────────

    string public constant PROTOCOL_NAME    = "GAIA";
    string public constant PROTOCOL_VERSION = "1.0.0";
    string public constant MISSION =
        "Remove the trust requirement from environmental compute.";

    // ────────────────────────────────────────────────────────────────────────────
    // Contract registry
    // ────────────────────────────────────────────────────────────────────────────

    address public immutable gaiaToken;
    address public immutable convictionVoting;
    address public immutable frozenOracle;
    address public immutable taskRegistry;
    address public immutable validationPool;
    address public immutable rewardDistributor;
    address public immutable timeLock;

    /// @notice Genesis timestamp
    uint256 public immutable genesisTimestamp;

    /// @notice Whether the protocol is paused (emergency only, requires 75% quorum)
    bool public paused;

    // ────────────────────────────────────────────────────────────────────────────
    // Events
    // ────────────────────────────────────────────────────────────────────────────

    event GenesisDeployment(
        address indexed gaiaToken,
        address indexed taskRegistry,
        address indexed validationPool,
        uint256 timestamp
    );

    event ProtocolPaused(address triggeredBy, uint256 timestamp);
    event ProtocolUnpaused(address triggeredBy, uint256 timestamp);

    // ────────────────────────────────────────────────────────────────────────────
    // Constructor
    // ────────────────────────────────────────────────────────────────────────────

    constructor(
        address _gaiaToken,
        address _convictionVoting,
        address _frozenOracle,
        address _taskRegistry,
        address _validationPool,
        address _rewardDistributor,
        address _timeLock
    ) {
        require(_gaiaToken         != address(0), "GP: zero gaiaToken");
        require(_convictionVoting  != address(0), "GP: zero convictionVoting");
        require(_frozenOracle      != address(0), "GP: zero frozenOracle");
        require(_taskRegistry      != address(0), "GP: zero taskRegistry");
        require(_validationPool    != address(0), "GP: zero validationPool");
        require(_rewardDistributor != address(0), "GP: zero rewardDistributor");
        require(_timeLock          != address(0), "GP: zero timeLock");

        gaiaToken         = _gaiaToken;
        convictionVoting  = _convictionVoting;
        frozenOracle      = _frozenOracle;
        taskRegistry      = _taskRegistry;
        validationPool    = _validationPool;
        rewardDistributor = _rewardDistributor;
        timeLock          = _timeLock;

        genesisTimestamp = block.timestamp;

        emit GenesisDeployment(_gaiaToken, _taskRegistry, _validationPool, block.timestamp);
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Emergency pause (ConvictionVoting only)
    // ────────────────────────────────────────────────────────────────────────────

    function pause() external {
        require(msg.sender == convictionVoting, "GP: not governance");
        paused = true;
        emit ProtocolPaused(msg.sender, block.timestamp);
    }

    function unpause() external {
        require(msg.sender == convictionVoting, "GP: not governance");
        paused = false;
        emit ProtocolUnpaused(msg.sender, block.timestamp);
    }

    // ────────────────────────────────────────────────────────────────────────────
    // View: Protocol summary
    // ────────────────────────────────────────────────────────────────────────────

    struct ProtocolInfo {
        string name;
        string version;
        string mission;
        address gaiaToken;
        address convictionVoting;
        address frozenOracle;
        address taskRegistry;
        address validationPool;
        address rewardDistributor;
        address timeLock;
        uint256 genesisTimestamp;
        bool paused;
    }

    function protocolInfo() external view returns (ProtocolInfo memory) {
        return ProtocolInfo({
            name:              PROTOCOL_NAME,
            version:           PROTOCOL_VERSION,
            mission:           MISSION,
            gaiaToken:         gaiaToken,
            convictionVoting:  convictionVoting,
            frozenOracle:      frozenOracle,
            taskRegistry:      taskRegistry,
            validationPool:    validationPool,
            rewardDistributor: rewardDistributor,
            timeLock:          timeLock,
            genesisTimestamp:  genesisTimestamp,
            paused:            paused
        });
    }
}
