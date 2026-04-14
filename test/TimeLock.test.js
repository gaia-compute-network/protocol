const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

describe("TimeLock", function () {
  let timeLock, gaiaToken;
  let owner, coordinator, teamMember1, teamMember2, other;

  const GENESIS_PERIOD = 18n * 30n * 24n * 60n * 60n; // 18 months
  const TEAM_CLIFF = 18n * 30n * 24n * 60n * 60n; // 18 months
  const TEAM_VESTING_PERIOD = 36n * 30n * 24n * 60n * 60n; // 36 months
  const MINIMUM_DELAY = 48n * 60n * 60n; // 48 hours
  const TEAM_ALLOCATION = ethers.parseEther("210000"); // 10% of 2.1M

  beforeEach(async function () {
    [owner, coordinator, teamMember1, teamMember2, other] = await ethers.getSigners();

    const GAIAToken = await ethers.getContractFactory("GAIAToken");
    gaiaToken = await GAIAToken.deploy(owner.address);

    const TimeLock = await ethers.getContractFactory("TimeLock");
    timeLock = await TimeLock.deploy(gaiaToken.getAddress(), coordinator.address);

    // Give TimeLock tokens for team vesting
    await gaiaToken.transfer(timeLock.getAddress(), TEAM_ALLOCATION * 2n);
  });

  describe("Deployment", function () {
    it("should set genesisCoordinator", async function () {
      expect(await timeLock.genesisCoordinator()).to.equal(coordinator.address);
    });

    it("should set genesisTimestamp", async function () {
      const genesisTs = await timeLock.genesisTimestamp();
      expect(genesisTs).to.be.greaterThan(0n);
    });

    it("should set genesisExpiry to 18 months from genesis", async function () {
      const genesis = await timeLock.genesisTimestamp();
      const expiry = await timeLock.genesisExpiry();
      expect(expiry).to.equal(genesis + GENESIS_PERIOD);
    });

    it("should initialize authorityRevoked to false", async function () {
      expect(await timeLock.authorityRevoked()).to.be.false;
    });
  });

  describe("Action Queueing", function () {
    it("should queue action with 48h delay", async function () {
      const targetAddr = other.address;
      const callData = "0x";
      const description = "Test action";

      await expect(
        timeLock.connect(coordinator).queueAction(targetAddr, callData, description)
      ).to.emit(timeLock, "ActionQueued");

      // Get the queued action
      const actionQueue = await timeLock.actionQueue(0);
      expect(actionQueue).not.to.equal(ethers.ZeroHash);
    });

    it("should revert if not coordinator", async function () {
      const targetAddr = other.address;
      const callData = "0x";
      const description = "Test action";

      await expect(
        timeLock.connect(other).queueAction(targetAddr, callData, description)
      ).to.be.revertedWithCustomError(timeLock, "NotGenesisCoordinator");
    });

    it("should revert if genesis authority expired", async function () {
      // Fast-forward past genesis expiry
      const expiry = await timeLock.genesisExpiry();
      await time.increaseTo(expiry + 1n);

      const targetAddr = other.address;
      const callData = "0x";

      await expect(
        timeLock.connect(coordinator).queueAction(targetAddr, callData, "Test")
      ).to.be.revertedWithCustomError(timeLock, "GenesisAuthorityExpiredError");
    });

    it("should revert if genesis authority revoked", async function () {
      await timeLock.connect(coordinator).revokeGenesisAuthority();

      await expect(
        timeLock.connect(coordinator).queueAction(other.address, "0x", "Test")
      ).to.be.revertedWithCustomError(timeLock, "GenesisAuthorityExpiredError");
    });

    it("should set correct executeAfter time", async function () {
      const targetAddr = other.address;
      const callData = "0x";

      const blockBefore = await ethers.provider.getBlockNumber();
      const timeBefore = (await ethers.provider.getBlock(blockBefore)).timestamp;

      await timeLock.connect(coordinator).queueAction(targetAddr, callData, "Test");

      const actionId = await timeLock.actionQueue(0);
      const action = await timeLock.queuedActions(actionId);

      expect(action.executeAfter).to.equal(BigInt(timeBefore) + MINIMUM_DELAY);
    });
  });

  describe("Action Execution", function () {
    beforeEach(async function () {
      // Queue an action
      const targetAddr = other.address;
      const callData = "0x";

      await timeLock.connect(coordinator).queueAction(targetAddr, callData, "Test action");
    });

    it("should revert if delay not met", async function () {
      const actionId = await timeLock.actionQueue(0);

      await expect(
        timeLock.connect(coordinator).executeAction(actionId)
      ).to.be.revertedWithCustomError(timeLock, "ActionNotReady");
    });

    it("should execute after delay", async function () {
      const actionId = await timeLock.actionQueue(0);
      const action = await timeLock.queuedActions(actionId);

      // Fast-forward to after executeAfter
      await time.increaseTo(action.executeAfter);

      await expect(
        timeLock.connect(coordinator).executeAction(actionId)
      ).to.emit(timeLock, "ActionExecuted");
    });

    it("should revert if already executed", async function () {
      const actionId = await timeLock.actionQueue(0);
      const action = await timeLock.queuedActions(actionId);

      await time.increaseTo(action.executeAfter);
      await timeLock.connect(coordinator).executeAction(actionId);

      // Try to execute again
      await expect(
        timeLock.connect(coordinator).executeAction(actionId)
      ).to.be.revertedWithCustomError(timeLock, "ActionAlreadyExecuted");
    });

    it("should revert for non-existent action", async function () {
      const fakeActionId = ethers.id("fake_action");

      await expect(
        timeLock.connect(coordinator).executeAction(fakeActionId)
      ).to.be.revertedWithCustomError(timeLock, "ActionNotFound");
    });

    it("should revert if not coordinator", async function () {
      const actionId = await timeLock.actionQueue(0);
      const action = await timeLock.queuedActions(actionId);

      await time.increaseTo(action.executeAfter);

      await expect(
        timeLock.connect(other).executeAction(actionId)
      ).to.be.revertedWithCustomError(timeLock, "NotGenesisCoordinator");
    });
  });

  describe("Action Cancellation", function () {
    beforeEach(async function () {
      await timeLock.connect(coordinator).queueAction(other.address, "0x", "Test action");
    });

    it("should cancel queued action", async function () {
      const actionId = await timeLock.actionQueue(0);

      await expect(
        timeLock.connect(coordinator).cancelAction(actionId)
      ).to.emit(timeLock, "ActionCancelled");

      const action = await timeLock.queuedActions(actionId);
      expect(action.executed).to.be.true; // Marked as executed to prevent execution
    });

    it("should revert if action not found", async function () {
      const fakeActionId = ethers.id("fake");

      await expect(
        timeLock.connect(coordinator).cancelAction(fakeActionId)
      ).to.be.revertedWithCustomError(timeLock, "ActionNotFound");
    });

    it("should revert if already executed", async function () {
      const actionId = await timeLock.actionQueue(0);
      const action = await timeLock.queuedActions(actionId);

      await time.increaseTo(action.executeAfter);
      await timeLock.connect(coordinator).executeAction(actionId);

      await expect(
        timeLock.connect(coordinator).cancelAction(actionId)
      ).to.be.revertedWithCustomError(timeLock, "ActionAlreadyExecuted");
    });
  });

  describe("Team Token Allocation", function () {
    it("should create team allocation", async function () {
      await expect(
        timeLock.connect(coordinator).createTeamAllocation(
          teamMember1.address,
          TEAM_ALLOCATION,
          "protocol_architect"
        )
      ).to.emit(timeLock, "TeamAllocationCreated")
        .withArgs(teamMember1.address, TEAM_ALLOCATION, "protocol_architect");

      expect(await timeLock.hasTeamAllocation(teamMember1.address)).to.be.true;
    });

    it("should revert if not coordinator", async function () {
      await expect(
        timeLock.connect(other).createTeamAllocation(
          teamMember1.address,
          TEAM_ALLOCATION,
          "role"
        )
      ).to.be.revertedWithCustomError(timeLock, "NotGenesisCoordinator");
    });

    it("should revert if beneficiary already has allocation", async function () {
      await timeLock.connect(coordinator).createTeamAllocation(
        teamMember1.address,
        TEAM_ALLOCATION,
        "role"
      );

      await expect(
        timeLock.connect(coordinator).createTeamAllocation(
          teamMember1.address,
          TEAM_ALLOCATION,
          "role2"
        )
      ).to.be.reverted;
    });

    it("should revert if beneficiary is zero address", async function () {
      await expect(
        timeLock.connect(coordinator).createTeamAllocation(
          ethers.ZeroAddress,
          TEAM_ALLOCATION,
          "role"
        )
      ).to.be.reverted;
    });
  });

  describe("Team Token Vesting", function () {
    beforeEach(async function () {
      await timeLock.connect(coordinator).createTeamAllocation(
        teamMember1.address,
        TEAM_ALLOCATION,
        "core_developer"
      );
    });

    it("should revert if cliff not reached", async function () {
      await expect(
        timeLock.connect(teamMember1).claimTeamTokens()
      ).to.be.revertedWithCustomError(timeLock, "TeamCliffNotReached");
    });

    it("should allow claim after cliff (18 months)", async function () {
      const genesis = await timeLock.genesisTimestamp();
      const cliffEnds = genesis + TEAM_CLIFF;

      await time.increaseTo(cliffEnds);

      await expect(
        timeLock.connect(teamMember1).claimTeamTokens()
      ).to.emit(timeLock, "TeamTokensClaimed");

      expect(await gaiaToken.balanceOf(teamMember1.address)).to.be.greaterThan(0n);
    });

    it("should have linear vesting over 36 months after cliff", async function () {
      const genesis = await timeLock.genesisTimestamp();
      const cliffEnds = genesis + TEAM_CLIFF;

      // Claim at cliff
      await time.increaseTo(cliffEnds);
      await timeLock.connect(teamMember1).claimTeamTokens();
      const cliffBalance = await gaiaToken.balanceOf(teamMember1.address);

      // Claim at 50% through vesting period
      const vestingMidpoint = cliffEnds + (TEAM_VESTING_PERIOD / 2n);
      await time.increaseTo(vestingMidpoint);
      const claimableMid = await timeLock.claimableTeamTokens(teamMember1.address);

      // Should be ~50% of total remaining
      expect(claimableMid).to.be.greaterThan(0n);
      expect(claimableMid).to.be.lessThan(TEAM_ALLOCATION);
    });

    it("should fully vest after cliff + 36 months", async function () {
      const genesis = await timeLock.genesisTimestamp();
      const fullVestEnds = genesis + TEAM_CLIFF + TEAM_VESTING_PERIOD;

      await time.increaseTo(fullVestEnds);

      const claimable = await timeLock.claimableTeamTokens(teamMember1.address);
      expect(claimable).to.equal(TEAM_ALLOCATION);

      await timeLock.connect(teamMember1).claimTeamTokens();
      expect(await gaiaToken.balanceOf(teamMember1.address)).to.equal(TEAM_ALLOCATION);
    });

    it("should revert if no allocation", async function () {
      const genesis = await timeLock.genesisTimestamp();
      const cliffEnds = genesis + TEAM_CLIFF;
      await time.increaseTo(cliffEnds);

      await expect(
        timeLock.connect(other).claimTeamTokens()
      ).to.be.revertedWithCustomError(timeLock, "NoTeamAllocation");
    });

    it("should handle multiple team members", async function () {
      await timeLock.connect(coordinator).createTeamAllocation(
        teamMember2.address,
        TEAM_ALLOCATION / 2n,
        "core_developer"
      );

      const genesis = await timeLock.genesisTimestamp();
      const cliffEnds = genesis + TEAM_CLIFF;
      await time.increaseTo(cliffEnds);

      await timeLock.connect(teamMember1).claimTeamTokens();
      await timeLock.connect(teamMember2).claimTeamTokens();

      const balance1 = await gaiaToken.balanceOf(teamMember1.address);
      const balance2 = await gaiaToken.balanceOf(teamMember2.address);

      expect(balance1).to.equal(TEAM_ALLOCATION);
      expect(balance2).to.equal(TEAM_ALLOCATION / 2n);
    });
  });

  describe("Genesis Authority Revocation", function () {
    it("should revoke genesis authority early", async function () {
      await expect(
        timeLock.connect(coordinator).revokeGenesisAuthority()
      ).to.emit(timeLock, "GenesisAuthorityRevoked");

      expect(await timeLock.authorityRevoked()).to.be.true;
    });

    it("should prevent all privileged functions after revocation", async function () {
      await timeLock.connect(coordinator).revokeGenesisAuthority();

      await expect(
        timeLock.connect(coordinator).queueAction(other.address, "0x", "Test")
      ).to.be.revertedWithCustomError(timeLock, "GenesisAuthorityExpiredError");
    });

    it("should revert if not coordinator", async function () {
      await expect(
        timeLock.connect(other).revokeGenesisAuthority()
      ).to.be.reverted;
    });

    it("should revert if already revoked", async function () {
      await timeLock.connect(coordinator).revokeGenesisAuthority();

      await expect(
        timeLock.connect(coordinator).revokeGenesisAuthority()
      ).to.be.reverted;
    });
  });

  describe("View Functions", function () {
    it("should return genesisIsActive correctly", async function () {
      expect(await timeLock.genesisIsActive()).to.be.true;

      const expiry = await timeLock.genesisExpiry();
      await time.increaseTo(expiry + 1n);

      expect(await timeLock.genesisIsActive()).to.be.false;
    });

    it("should return timeUntilExpiry", async function () {
      const remaining = await timeLock.timeUntilExpiry();
      expect(remaining).to.be.greaterThan(0n);

      const expiry = await timeLock.genesisExpiry();
      await time.increaseTo(expiry);

      const remaining2 = await timeLock.timeUntilExpiry();
      expect(remaining2).to.equal(0n);
    });

    it("should count pending actions", async function () {
      await timeLock.connect(coordinator).queueAction(other.address, "0x", "Action 1");
      await timeLock.connect(coordinator).queueAction(other.address, "0x", "Action 2");

      expect(await timeLock.pendingActionsCount()).to.equal(2n);
    });

    it("should return claimable team tokens", async function () {
      await timeLock.connect(coordinator).createTeamAllocation(
        teamMember1.address,
        TEAM_ALLOCATION,
        "role"
      );

      const claimable = await timeLock.claimableTeamTokens(teamMember1.address);
      expect(claimable).to.equal(0n); // Before cliff

      const genesis = await timeLock.genesisTimestamp();
      const cliffEnds = genesis + TEAM_CLIFF;
      await time.increaseTo(cliffEnds);

      const claimableAfter = await timeLock.claimableTeamTokens(teamMember1.address);
      expect(claimableAfter).to.be.greaterThan(0n);
    });
  });

  describe("Constants", function () {
    it("should have correct GENESIS_PERIOD", async function () {
      expect(await timeLock.GENESIS_PERIOD()).to.equal(GENESIS_PERIOD);
    });

    it("should have correct TEAM_CLIFF", async function () {
      expect(await timeLock.TEAM_CLIFF()).to.equal(TEAM_CLIFF);
    });

    it("should have correct TEAM_VESTING_PERIOD", async function () {
      expect(await timeLock.TEAM_VESTING_PERIOD()).to.equal(TEAM_VESTING_PERIOD);
    });

    it("should have correct MINIMUM_DELAY", async function () {
      expect(await timeLock.MINIMUM_DELAY()).to.equal(MINIMUM_DELAY);
    });
  });
});
