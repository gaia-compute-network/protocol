// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract MockRewardDistributor {
    function distributeRewards(
        uint256 taskId,
        uint256 totalReward,
        address[] calldata winners
    ) external {
        // Mock implementation
    }

    function distributePublicGoodBonus(uint256 taskId, address[] calldata miners) external {
        // Mock implementation
    }
}
