// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract MockConvictionVoting {
    function executeOracleUpdate(address oracle, bytes32 newHash, string calldata newCID) external {
        (bool success,) = oracle.call(
            abi.encodeWithSignature("executeOracleUpdate(bytes32,string)", newHash, newCID)
        );
        require(success, "Call failed");
    }
}
