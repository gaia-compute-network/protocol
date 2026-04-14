// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract MockConvictionVoting {
    function executeOracleUpdate(address oracle, bytes32 newHash, string calldata newCID) external {
        (bool success, bytes memory returnData) = oracle.call(
            abi.encodeWithSignature("executeOracleUpdate(bytes32,string)", newHash, newCID)
        );
        if (!success) {
            // Bubble up the original revert reason so tests can match custom errors
            assembly {
                revert(add(returnData, 32), mload(returnData))
            }
        }
    }
}
