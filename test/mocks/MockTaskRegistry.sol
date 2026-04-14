// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract MockTaskRegistry {
    mapping(uint256 => bool) public isReadyForValidation;
    mapping(uint256 => MinerSubmission[]) public submissions;

    struct MinerSubmission {
        address miner;
        bytes32 resultFingerprint;
    }

    function setReadyForValidation(uint256 taskId, bool ready) external {
        isReadyForValidation[taskId] = ready;
    }

    function setSubmissions(uint256 taskId, MinerSubmission[] calldata subs) external {
        delete submissions[taskId];
        for (uint256 i = 0; i < subs.length; i++) {
            submissions[taskId].push(subs[i]);
        }
    }

    function getSubmissions(uint256 taskId) external view returns (MinerSubmission[] memory) {
        return submissions[taskId];
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
