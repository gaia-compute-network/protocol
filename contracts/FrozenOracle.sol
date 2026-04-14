// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title FrozenOracle
 * @notice The FrozenOracle is GAIA's constitutional boundary for what the network
 *         is allowed to compute. It is a binary classifier: jobs are either
 *         "in-scope" (environmental science) or "out-of-scope" (everything else).
 *
 * ── Why "Frozen"? ───────────────────────────────────────────────────────────
 *
 * The temptation for any successful protocol is to expand scope. A hedge fund
 * offers $3M to add financial model verification. A government offers a contract
 * to run surveillance inference. Each expansion looks reasonable in isolation.
 *
 * The Frozen Oracle makes scope expansion constitutionally difficult:
 *   - The oracle model hash is committed at genesis
 *   - Updating it requires a 90%+ supermajority hard fork vote
 *   - The vote window opens only once every 10 years (ORACLE_UPDATE_PERIOD)
 *   - No emergency override. No admin key. No backdoor.
 *
 * This is not stubbornness. It is the lesson from every protocol that started
 * with "just environmental data" and ended up running financial models.
 *
 * ── What the Oracle classifies ──────────────────────────────────────────────
 *
 * IN-SCOPE (allowed):
 *   - Species identification from camera trap images
 *   - Deforestation detection from satellite imagery
 *   - Ocean temperature / acidification trend inference
 *   - Biodiversity index computation (GBIF, iNaturalist data)
 *   - Carbon sequestration estimation from LiDAR data
 *   - Acoustic ecology (bird song, whale call identification)
 *   - Wildfire smoke / particulate matter classification
 *   - Marine microplastics detection from spectroscopy
 *
 * OUT-OF-SCOPE (permanently blocked):
 *   - Financial model inference of any kind
 *   - Facial recognition or biometric identification
 *   - Medical diagnosis (separate regulatory domain)
 *   - Political content classification
 *   - Military / surveillance applications
 *
 * ── On-chain representation ─────────────────────────────────────────────────
 *
 * The oracle itself (a lightweight binary classifier) runs off-chain on miner
 * nodes. Its integrity is guaranteed by:
 *   1. The model weights hash (oracleModelHash) anchored in the genesis block
 *   2. Miners must prove they are using the correct model before submitting results
 *   3. The TaskRegistry checks the oracle signature before accepting any task
 *
 * @author GAIA Core Team
 * @custom:version 1.0.0
 */
contract FrozenOracle {

    // ────────────────────────────────────────────────────────────────────────────
    // Constants
    // ────────────────────────────────────────────────────────────────────────────

    /// @notice Minimum supermajority required to update the oracle (90%)
    uint256 public constant ORACLE_UPDATE_QUORUM_BPS = 9_000;

    /// @notice Once per decade oracle update window (in seconds)
    uint256 public constant ORACLE_UPDATE_PERIOD = 10 * 365 days;

    /// @notice Version string for the current oracle specification
    string public constant ORACLE_SPEC_VERSION = "gaia-oracle-v1.0";

    // ────────────────────────────────────────────────────────────────────────────
    // State
    // ────────────────────────────────────────────────────────────────────────────

    /// @notice SHA-256 hash of the frozen oracle model weights
    ///         (stored as bytes32 = first 32 bytes of the SHA-256 hex digest)
    bytes32 public oracleModelHash;

    /// @notice IPFS CID where the full oracle model weights can be downloaded
    ///         Miners are required to verify their local model against this hash
    string public oracleModelCID;

    /// @notice Genesis timestamp — when the oracle was locked
    uint256 public immutable genesisTimestamp;

    /// @notice Next possible update window (genesisTimestamp + ORACLE_UPDATE_PERIOD)
    uint256 public nextUpdateWindow;

    /// @notice Whether an update vote is currently in progress
    bool public updateVoteActive;

    /// @notice Address of the ConvictionVoting contract (set at genesis)
    address public immutable convictionVoting;

    /// @notice Canonical list of approved job type identifiers
    ///         These map to the oracle's in-scope classes
    bytes32[] public approvedJobTypes;
    mapping(bytes32 => bool) public isApprovedJobType;
    mapping(bytes32 => string) public jobTypeDescription;

    // ────────────────────────────────────────────────────────────────────────────
    // Events
    // ────────────────────────────────────────────────────────────────────────────

    event OracleInitialized(
        bytes32 indexed modelHash,
        string modelCID,
        uint256 genesisTimestamp
    );

    event JobTypeApproved(
        bytes32 indexed jobTypeId,
        string description
    );

    event OracleUpdateProposed(
        bytes32 indexed proposedHash,
        string proposedCID,
        uint256 voteWindowOpen
    );

    event OracleUpdated(
        bytes32 indexed oldHash,
        bytes32 indexed newHash,
        string newCID
    );

    // ────────────────────────────────────────────────────────────────────────────
    // Errors
    // ────────────────────────────────────────────────────────────────────────────

    error NotConvictionVoting();
    error UpdateWindowNotOpen();
    error JobTypeNotApproved(bytes32 jobTypeId);
    error OracleAlreadyInitialized();
    error ZeroHash();

    // ────────────────────────────────────────────────────────────────────────────
    // Constructor
    // ────────────────────────────────────────────────────────────────────────────

    /**
     * @param _convictionVoting  The ConvictionVoting governance contract address
     */
    constructor(address _convictionVoting) {
        require(_convictionVoting != address(0), "FrozenOracle: zero address");
        convictionVoting = _convictionVoting;
        genesisTimestamp = block.timestamp;
        nextUpdateWindow = block.timestamp + ORACLE_UPDATE_PERIOD;
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Genesis initialization (called once by the genesis ceremony)
    // ────────────────────────────────────────────────────────────────────────────

    /**
     * @notice Lock the oracle model hash at genesis. Can only be called once.
     * @param _modelHash  SHA-256 hash of the oracle model weights (bytes32)
     * @param _modelCID   IPFS CID of the oracle model for download
     */
    function initializeOracle(
        bytes32 _modelHash,
        string calldata _modelCID
    ) external {
        if (oracleModelHash != bytes32(0)) revert OracleAlreadyInitialized();
        if (_modelHash == bytes32(0)) revert ZeroHash();

        oracleModelHash = _modelHash;
        oracleModelCID = _modelCID;

        // Seed the approved job types at genesis
        _approveJobType(keccak256("species_identification"),
            "Species identification from camera trap or field images");
        _approveJobType(keccak256("deforestation_detection"),
            "Deforestation / land-cover change detection from satellite imagery");
        _approveJobType(keccak256("ocean_temperature_inference"),
            "Sea surface temperature / acidification trend inference");
        _approveJobType(keccak256("biodiversity_index"),
            "Biodiversity index computation from occurrence data (GBIF, iNaturalist)");
        _approveJobType(keccak256("carbon_sequestration"),
            "Carbon sequestration estimation from LiDAR / remote sensing");
        _approveJobType(keccak256("acoustic_ecology"),
            "Bioacoustic species identification (birds, marine mammals, insects)");
        _approveJobType(keccak256("wildfire_classification"),
            "Wildfire smoke, burn scar, or air quality classification");
        _approveJobType(keccak256("marine_microplastics"),
            "Microplastics detection from spectroscopy or image data");
        _approveJobType(keccak256("freivalds_demo"),
            "Protocol test / genesis demo — not for production use");

        emit OracleInitialized(_modelHash, _modelCID, block.timestamp);
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Job type validation (called by TaskRegistry before accepting any job)
    // ────────────────────────────────────────────────────────────────────────────

    /**
     * @notice Check whether a job type is approved by the oracle.
     *         Reverts if not approved — TaskRegistry uses this as a gate.
     * @param jobTypeId  keccak256 of the job type string
     */
    function requireApproved(bytes32 jobTypeId) external view {
        if (!isApprovedJobType[jobTypeId]) revert JobTypeNotApproved(jobTypeId);
    }

    /**
     * @notice Returns true if the job type is in-scope, false otherwise.
     *         Non-reverting version for off-chain queries.
     */
    function isInScope(bytes32 jobTypeId) external view returns (bool) {
        return isApprovedJobType[jobTypeId];
    }

    /**
     * @notice Helper: compute the job type ID for a string
     */
    function jobTypeId(string calldata jobTypeName) external pure returns (bytes32) {
        return keccak256(bytes(jobTypeName));
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Oracle update (90%+ supermajority, once per decade)
    // ────────────────────────────────────────────────────────────────────────────

    /**
     * @notice Propose an oracle model update. Only callable by ConvictionVoting
     *         after a 90%+ supermajority vote, and only within the update window.
     *
     * @param newModelHash  New oracle model weights hash
     * @param newModelCID   New IPFS CID
     */
    function executeOracleUpdate(
        bytes32 newModelHash,
        string calldata newModelCID
    ) external {
        if (msg.sender != convictionVoting) revert NotConvictionVoting();
        if (block.timestamp < nextUpdateWindow) revert UpdateWindowNotOpen();
        if (newModelHash == bytes32(0)) revert ZeroHash();

        bytes32 oldHash = oracleModelHash;
        oracleModelHash = newModelHash;
        oracleModelCID = newModelCID;
        nextUpdateWindow = block.timestamp + ORACLE_UPDATE_PERIOD;

        emit OracleUpdated(oldHash, newModelHash, newModelCID);
    }

    // ────────────────────────────────────────────────────────────────────────────
    // Internal helpers
    // ────────────────────────────────────────────────────────────────────────────

    function _approveJobType(bytes32 id, string memory description) internal {
        approvedJobTypes.push(id);
        isApprovedJobType[id] = true;
        jobTypeDescription[id] = description;
        emit JobTypeApproved(id, description);
    }

    // ────────────────────────────────────────────────────────────────────────────
    // View helpers
    // ────────────────────────────────────────────────────────────────────────────

    function approvedJobTypeCount() external view returns (uint256) {
        return approvedJobTypes.length;
    }

    function yearsUntilNextUpdateWindow() external view returns (uint256) {
        if (block.timestamp >= nextUpdateWindow) return 0;
        return (nextUpdateWindow - block.timestamp) / 365 days;
    }
}
