// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract MockValidationPool {
    function assignMiners(address taskRegistry, uint256 taskId, address[] calldata miners) external {
        (bool success,) = taskRegistry.call(
            abi.encodeWithSignature("assignMiners(uint256,address[])", taskId, miners)
        );
        require(success, "assignMiners failed");
    }

    function finalizeTaskVerified(
        address taskRegistry,
        uint256 taskId,
        bytes32 agreedFingerprint,
        address[] calldata slashedMiners
    ) external {
        (bool success,) = taskRegistry.call(
            abi.encodeWithSignature(
                "finalizeTaskVerified(uint256,bytes32,address[])",
                taskId,
                agreedFingerprint,
                slashedMiners
            )
        );
        require(success, "finalizeTaskVerified failed");
    }

    function finalizeTaskFailed(
        address taskRegistry,
        uint256 taskId,
        string calldata reason
    ) external {
        (bool success,) = taskRegistry.call(
            abi.encodeWithSignature("finalizeTaskFailed(uint256,string)", taskId, reason)
        );
        require(success, "finalizeTaskFailed failed");
    }
}
