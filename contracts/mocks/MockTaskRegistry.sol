// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract MockTaskRegistry {
    mapping(uint256 => bool) public isReadyForValidation;
    mapping(uint256 => MinerSubmission[]) public submissions;

    // Must match TaskRegistry.MinerSubmission exactly (same ABI encoding)
    struct MinerSubmission {
        address miner;
        bytes32 resultHash;
        bytes32 commitment;
        bytes32 resultFingerprint;
        uint256 submittedAt;
        bool slashed;
    }

    // Lightweight helper for test setup — only miner + fingerprint required
    struct SubmissionInput {
        address miner;
        bytes32 resultFingerprint;
    }

    function setReadyForValidation(uint256 taskId, bool ready) external {
        isReadyForValidation[taskId] = ready;
    }

    function setSubmissions(uint256 taskId, SubmissionInput[] calldata subs) external {
        delete submissions[taskId];
        for (uint256 i = 0; i < subs.length; i++) {
            submissions[taskId].push(MinerSubmission({
                miner: subs[i].miner,
                resultHash: bytes32(0),
                commitment: bytes32(0),
                resultFingerprint: subs[i].resultFingerprint,
                submittedAt: block.timestamp,
                slashed: false
            }));
        }
    }

    function getSubmissions(uint256 taskId) external view returns (MinerSubmission[] memory) {
        return submissions[taskId];
    }

    function getTaskReward(uint256 /*taskId*/) external pure returns (uint256) {
        return 1000 * 10**18; // Fixed mock reward
    }

    function assignMiners(uint256 taskId, address[] calldata miners) external {
        // Mock implementation
    }

    function finalizeTaskVerified(
        uint256 taskId,
        bytes32 agreedFingerprint,
        address[] calldata slashedMiners
    ) external {
        // Mock implementation
    }

    function finalizeTaskFailed(uint256 taskId, string calldata reason) external {
        // Mock implementation
    }
}
