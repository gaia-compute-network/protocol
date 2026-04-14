const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

describe("RewardDistributor", function () {
  let rewardDistributor, gaiaToken;
  let owner, validationPool, miner1, miner2, miner3, treasury;

  const MINER_SHARE_BPS = 6000n; // 60%
  const VALIDATOR_SHARE_BPS = 2500n; // 25%
  const TREASURY_SHARE_BPS = 1500n; // 15%
  const VESTING_PERIOD = 90n * 24n * 60n * 60n; // 90 days
  const PUBLIC_GOOD_BONUS_BPS = 1000n; // 10%

  beforeEach(async function () {
    [owner, validationPool, miner1, miner2, miner3, treasury] = await ethers.getSigners();

    const GAIAToken = await ethers.getContractFactory("GAIAToken");
    gaiaToken = await GAIAToken.deploy(owner.address);

    // RewardDistributor now takes only gaiaToken + treasury (circular dep fix)
    const RewardDistributor = await ethers.getContractFactory("RewardDistributor");
    rewardDistributor = await RewardDistributor.deploy(
      await gaiaToken.getAddress(),
      treasury.address
    );

    // Set validationPool post-deployment (only owner can do this — Sprint 2 security fix)
    await rewardDistributor.setValidationPool(validationPool.address);

    // Give reward distributor tokens for distribution
    await gaiaToken.transfer(rewardDistributor.getAddress(), ethers.parseEther("10000000"));
  });

  describe("Deployment", function () {
    it("should set gaiaToken address", async function () {
      expect(await rewardDistributor.gaiaToken()).to.equal(await gaiaToken.getAddress());
    });

    it("should set validationPool address after setValidationPool()", async function () {
      expect(await rewardDistributor.validationPool()).to.equal(validationPool.address);
    });

    it("should set treasury address", async function () {
      expect(await rewardDistributor.treasury()).to.equal(treasury.address);
    });
  });

  // ── Security: setValidationPool() access control (Sprint 2 fix) ─────────────
  describe("setValidationPool() Access Control", function () {
    let freshDistributor;

    beforeEach(async function () {
      const RewardDistributor = await ethers.getContractFactory("RewardDistributor");
      freshDistributor = await RewardDistributor.deploy(
        await gaiaToken.getAddress(),
        treasury.address
      );
    });

    it("should allow owner to call setValidationPool()", async function () {
      await expect(
        freshDistributor.connect(owner).setValidationPool(validationPool.address)
      ).to.emit(freshDistributor, "ValidationPoolSet")
        .withArgs(validationPool.address);
    });

    it("should revert if non-owner calls setValidationPool()", async function () {
      await expect(
        freshDistributor.connect(miner1).setValidationPool(validationPool.address)
      ).to.be.revertedWithCustomError(freshDistributor, "NotOwner");
    });

    it("should revert if setValidationPool() called twice", async function () {
      await freshDistributor.connect(owner).setValidationPool(validationPool.address);

      await expect(
        freshDistributor.connect(owner).setValidationPool(validationPool.address)
      ).to.be.revertedWith("RD: validationPool already set");
    });

    it("should revert if validationPool is zero address", async function () {
      await expect(
        freshDistributor.connect(owner).setValidationPool(ethers.ZeroAddress)
      ).to.be.revertedWith("RD: zero validationPool");
    });
  });

  describe("Reward Distribution (60/25/15 split)", function () {
    it("should distribute rewards with correct shares", async function () {
      const totalReward = ethers.parseEther("1000");
      const miners = [miner1.address, miner2.address, miner3.address];

      const minerPool = (totalReward * MINER_SHARE_BPS) / 10000n;
      const perMiner = minerPool / 3n;
      const treasuryPool = (totalReward * VALIDATOR_SHARE_BPS) / 10000n +
                           (totalReward * TREASURY_SHARE_BPS) / 10000n;

      await rewardDistributor.connect(validationPool).distributeRewards(1, totalReward, miners);

      expect(await rewardDistributor.totalRewardsDistributed()).to.equal(totalReward);

      // Check vesting schedules created
      const schedule1 = await rewardDistributor.getVestingSchedules(miner1.address);
      expect(schedule1.length).to.equal(1);
      expect(schedule1[0].totalAmount).to.equal(perMiner);
    });

    it("should split rewards among multiple miners equally", async function () {
      const totalReward = ethers.parseEther("600");
      const miners = [miner1.address, miner2.address];

      const minerPool = (totalReward * MINER_SHARE_BPS) / 10000n;
      const perMiner = minerPool / 2n;

      await rewardDistributor.connect(validationPool).distributeRewards(1, totalReward, miners);

      const schedule1 = await rewardDistributor.getVestingSchedules(miner1.address);
      const schedule2 = await rewardDistributor.getVestingSchedules(miner2.address);

      expect(schedule1[0].totalAmount).to.equal(perMiner);
      expect(schedule2[0].totalAmount).to.equal(perMiner);
    });

    it("should revert if not validationPool", async function () {
      const totalReward = ethers.parseEther("1000");
      const miners = [miner1.address];

      await expect(
        rewardDistributor.connect(owner).distributeRewards(1, totalReward, miners)
      ).to.be.revertedWithCustomError(rewardDistributor, "NotValidationPool");
    });

    it("should revert with no winners", async function () {
      const totalReward = ethers.parseEther("1000");

      await expect(
        rewardDistributor.connect(validationPool).distributeRewards(1, totalReward, [])
      ).to.be.reverted;
    });
  });

  describe("Vesting Schedule", function () {
    beforeEach(async function () {
      const totalReward = ethers.parseEther("1000");
      const miners = [miner1.address];

      await rewardDistributor.connect(validationPool).distributeRewards(1, totalReward, miners);
    });

    it("should create vesting schedule", async function () {
      const schedules = await rewardDistributor.getVestingSchedules(miner1.address);
      expect(schedules.length).to.equal(1);
      expect(schedules[0].taskId).to.equal(1n);
      expect(schedules[0].claimedAmount).to.equal(0n);
    });

    it("should emit RewardVestingCreated", async function () {
      const totalReward = ethers.parseEther("1000");
      const miners = [miner1.address];

      await expect(
        rewardDistributor.connect(validationPool).distributeRewards(2, totalReward, miners)
      ).to.emit(rewardDistributor, "RewardVestingCreated");
    });

    it("should track totalUnvested", async function () {
      const schedules = await rewardDistributor.getVestingSchedules(miner1.address);
      const unvested = await rewardDistributor.totalUnvested(miner1.address);

      expect(unvested).to.equal(schedules[0].totalAmount);
    });

    it("should track vestingScheduleCount", async function () {
      expect(await rewardDistributor.vestingScheduleCount(miner1.address)).to.equal(1n);
    });
  });

  describe("Linear Vesting (90 days)", function () {
    beforeEach(async function () {
      const totalReward = ethers.parseEther("1000");
      const miners = [miner1.address];

      await rewardDistributor.connect(validationPool).distributeRewards(1, totalReward, miners);
    });

    it("should have 0 vested at start", async function () {
      const schedules = await rewardDistributor.getVestingSchedules(miner1.address);
      expect(schedules[0].totalAmount).to.be.greaterThan(0n);

      const vested = await rewardDistributor.vestedBalance(miner1.address);
      expect(vested).to.equal(0n);
    });

    it("should have partial vesting at 45 days", async function () {
      const schedules = await rewardDistributor.getVestingSchedules(miner1.address);
      const totalAmount = schedules[0].totalAmount;

      // Advance 45 days (halfway)
      await time.increase(45n * 24n * 60n * 60n);

      const vested = await rewardDistributor.vestedBalance(miner1.address);
      const expected = (totalAmount / 2n);

      expect(vested).to.be.closeTo(expected, ethers.parseEther("1"));
    });

    it("should have full vesting after 90 days", async function () {
      const schedules = await rewardDistributor.getVestingSchedules(miner1.address);
      const totalAmount = schedules[0].totalAmount;

      // Advance 90 days
      await time.increase(VESTING_PERIOD);

      const vested = await rewardDistributor.vestedBalance(miner1.address);
      expect(vested).to.equal(totalAmount);
    });

    it("should remain fully vested after 90 days", async function () {
      const schedules = await rewardDistributor.getVestingSchedules(miner1.address);
      const totalAmount = schedules[0].totalAmount;

      // Advance well past 90 days
      await time.increase(200n * 24n * 60n * 60n);

      const vested = await rewardDistributor.vestedBalance(miner1.address);
      expect(vested).to.equal(totalAmount);
    });
  });

  describe("Claiming Vested Rewards", function () {
    beforeEach(async function () {
      const totalReward = ethers.parseEther("1000");
      const miners = [miner1.address, miner2.address];

      await rewardDistributor.connect(validationPool).distributeRewards(1, totalReward, miners);
    });

    it("should allow claim after partial vesting", async function () {
      // Advance 45 days
      await time.increase(45n * 24n * 60n * 60n);

      const schedules = await rewardDistributor.getVestingSchedules(miner1.address);
      const totalAmount = schedules[0].totalAmount;
      const expectedClaimable = totalAmount / 2n;

      const initialBalance = await gaiaToken.balanceOf(miner1.address);

      await rewardDistributor.connect(miner1).claimVestedRewards();

      const finalBalance = await gaiaToken.balanceOf(miner1.address);
      expect(finalBalance - initialBalance).to.be.closeTo(expectedClaimable, ethers.parseEther("1"));
    });

    it("should allow claim after full vesting", async function () {
      await time.increase(VESTING_PERIOD);

      const schedules = await rewardDistributor.getVestingSchedules(miner1.address);
      const totalAmount = schedules[0].totalAmount;

      const initialBalance = await gaiaToken.balanceOf(miner1.address);

      await rewardDistributor.connect(miner1).claimVestedRewards();

      const finalBalance = await gaiaToken.balanceOf(miner1.address);
      expect(finalBalance - initialBalance).to.equal(totalAmount);
    });

    it("should revert if nothing to claim", async function () {
      // miner3 has no vesting schedule at all → NothingToClaim
      await expect(
        rewardDistributor.connect(miner3).claimVestedRewards()
      ).to.be.revertedWithCustomError(rewardDistributor, "NothingToClaim");
    });

    it("should emit RewardClaimed event", async function () {
      await time.increase(VESTING_PERIOD);

      await expect(
        rewardDistributor.connect(miner1).claimVestedRewards()
      ).to.emit(rewardDistributor, "RewardClaimed");
    });

    it("should update totalRewardsClaimed", async function () {
      await time.increase(VESTING_PERIOD);

      const schedules = await rewardDistributor.getVestingSchedules(miner1.address);
      const claimAmount = schedules[0].totalAmount;

      await rewardDistributor.connect(miner1).claimVestedRewards();

      expect(await rewardDistributor.totalRewardsClaimed()).to.equal(claimAmount);
    });

    it("should allow incremental claims", async function () {
      // First claim at 45 days
      await time.increase(45n * 24n * 60n * 60n);

      const schedules1 = await rewardDistributor.getVestingSchedules(miner1.address);
      const firstClaimable = (schedules1[0].totalAmount / 2n);

      await rewardDistributor.connect(miner1).claimVestedRewards();

      // Second claim at 90 days
      await time.increase(45n * 24n * 60n * 60n);

      const schedules2 = await rewardDistributor.getVestingSchedules(miner1.address);
      const secondClaimable = schedules2[0].totalAmount - (schedules2[0].totalAmount / 2n);

      await rewardDistributor.connect(miner1).claimVestedRewards();

      expect(await rewardDistributor.totalRewardsClaimed()).to.be.closeTo(
        schedules2[0].totalAmount,
        ethers.parseEther("1")
      );
    });
  });

  describe("Public Good Bonus", function () {
    it("should distribute public good bonus", async function () {
      const miners = [miner1.address, miner2.address];

      const bonusPerMiner = (ethers.parseEther("100") * PUBLIC_GOOD_BONUS_BPS) / 10000n;

      await rewardDistributor.connect(validationPool).distributePublicGoodBonus(1, miners);

      expect(await rewardDistributor.totalPublicGoodBonusPaid()).to.equal(bonusPerMiner * 2n);
    });

    it("should create vesting schedules for bonus", async function () {
      const miners = [miner1.address];

      await rewardDistributor.connect(validationPool).distributePublicGoodBonus(1, miners);

      const schedules = await rewardDistributor.getVestingSchedules(miner1.address);
      expect(schedules.length).to.equal(1);
    });

    it("should emit PublicGoodBonusPaid event", async function () {
      const miners = [miner1.address];

      await expect(
        rewardDistributor.connect(validationPool).distributePublicGoodBonus(1, miners)
      ).to.emit(rewardDistributor, "PublicGoodBonusPaid");
    });

    it("should revert if not validationPool", async function () {
      const miners = [miner1.address];

      await expect(
        rewardDistributor.connect(owner).distributePublicGoodBonus(1, miners)
      ).to.be.revertedWithCustomError(rewardDistributor, "NotValidationPool");
    });
  });

  describe("Claimable Balance View", function () {
    beforeEach(async function () {
      const totalReward = ethers.parseEther("1000");
      const miners = [miner1.address];

      await rewardDistributor.connect(validationPool).distributeRewards(1, totalReward, miners);
    });

    it("should return 0 claimable at start", async function () {
      const claimable = await rewardDistributor.claimableBalance(miner1.address);
      expect(claimable).to.equal(0n);
    });

    it("should return partial claimable at 50% vesting", async function () {
      await time.increase(45n * 24n * 60n * 60n);

      const schedules = await rewardDistributor.getVestingSchedules(miner1.address);
      const claimable = await rewardDistributor.claimableBalance(miner1.address);

      expect(claimable).to.be.closeTo(schedules[0].totalAmount / 2n, ethers.parseEther("1"));
    });

    it("should return full claimable after vesting", async function () {
      await time.increase(VESTING_PERIOD);

      const schedules = await rewardDistributor.getVestingSchedules(miner1.address);
      const claimable = await rewardDistributor.claimableBalance(miner1.address);

      expect(claimable).to.equal(schedules[0].totalAmount);
    });

    it("should decrease after partial claim", async function () {
      await time.increase(45n * 24n * 60n * 60n);
      const claimableBefore = await rewardDistributor.claimableBalance(miner1.address);

      await rewardDistributor.connect(miner1).claimVestedRewards();

      await time.increase(45n * 24n * 60n * 60n);
      const claimableAfter = await rewardDistributor.claimableBalance(miner1.address);

      expect(claimableAfter).to.be.lessThan(claimableBefore);
    });
  });

  describe("Multiple Tasks Vesting", function () {
    it("should handle multiple vesting schedules", async function () {
      const reward1 = ethers.parseEther("500");
      const reward2 = ethers.parseEther("300");

      await rewardDistributor.connect(validationPool).distributeRewards(1, reward1, [miner1.address]);
      await rewardDistributor.connect(validationPool).distributeRewards(2, reward2, [miner1.address]);

      const schedules = await rewardDistributor.getVestingSchedules(miner1.address);
      expect(schedules.length).to.equal(2);

      const expected1 = (reward1 * MINER_SHARE_BPS) / 10000n;
      const expected2 = (reward2 * MINER_SHARE_BPS) / 10000n;

      expect(schedules[0].totalAmount).to.equal(expected1);
      expect(schedules[1].totalAmount).to.equal(expected2);
    });

    it("should claim from multiple schedules simultaneously", async function () {
      const reward1 = ethers.parseEther("500");
      const reward2 = ethers.parseEther("300");

      await rewardDistributor.connect(validationPool).distributeRewards(1, reward1, [miner1.address]);
      await rewardDistributor.connect(validationPool).distributeRewards(2, reward2, [miner1.address]);

      await time.increase(VESTING_PERIOD);

      const schedules = await rewardDistributor.getVestingSchedules(miner1.address);
      const totalExpected = schedules[0].totalAmount + schedules[1].totalAmount;

      const initialBalance = await gaiaToken.balanceOf(miner1.address);
      await rewardDistributor.connect(miner1).claimVestedRewards();
      const finalBalance = await gaiaToken.balanceOf(miner1.address);

      expect(finalBalance - initialBalance).to.equal(totalExpected);
    });
  });

  describe("Constants", function () {
    it("should have MINER_SHARE_BPS = 60%", async function () {
      expect(await rewardDistributor.MINER_SHARE_BPS()).to.equal(MINER_SHARE_BPS);
    });

    it("should have VALIDATOR_SHARE_BPS = 25%", async function () {
      expect(await rewardDistributor.VALIDATOR_SHARE_BPS()).to.equal(VALIDATOR_SHARE_BPS);
    });

    it("should have TREASURY_SHARE_BPS = 15%", async function () {
      expect(await rewardDistributor.TREASURY_SHARE_BPS()).to.equal(TREASURY_SHARE_BPS);
    });

    it("should have VESTING_PERIOD = 90 days", async function () {
      const period = await rewardDistributor.VESTING_PERIOD();
      expect(period).to.equal(VESTING_PERIOD);
    });
  });
});
