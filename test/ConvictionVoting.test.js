const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

describe("ConvictionVoting", function () {
  let convictionVoting, gaiaToken;
  let owner, voter1, voter2, voter3, targetContract;

  const DECAY_NUMERATOR = 9999n;
  const DECAY_DENOMINATOR = 10000n;
  const STANDARD_QUORUM_BPS = 3300n; // 33%
  const EMERGENCY_QUORUM_BPS = 7500n; // 75%
  const ORACLE_QUORUM_BPS = 9000n; // 90%
  const MAX_CONVICTION_PER_TOKEN = 1000000n;
  const MIN_CONVICTION_BLOCKS = 40320n; // ~7 days

  const LOCK_AMOUNT = ethers.parseEther("1000");

  beforeEach(async function () {
    [owner, voter1, voter2, voter3, targetContract] = await ethers.getSigners();

    const GAIAToken = await ethers.getContractFactory("GAIAToken");
    gaiaToken = await GAIAToken.deploy(owner.address);

    const ConvictionVoting = await ethers.getContractFactory("ConvictionVoting");
    convictionVoting = await ConvictionVoting.deploy(gaiaToken.getAddress());

    // Distribute tokens
    await gaiaToken.transfer(voter1.address, LOCK_AMOUNT * 2n);
    await gaiaToken.transfer(voter2.address, LOCK_AMOUNT);
    await gaiaToken.transfer(voter3.address, LOCK_AMOUNT);
  });

  describe("Token Locking", function () {
    it("should lock tokens", async function () {
      await gaiaToken.connect(voter1).approve(convictionVoting.getAddress(), LOCK_AMOUNT);

      await expect(
        convictionVoting.connect(voter1).lockTokens(LOCK_AMOUNT)
      ).to.emit(convictionVoting, "TokensLocked")
        .withArgs(voter1.address, LOCK_AMOUNT);

      const voter = await convictionVoting.voterStates(voter1.address);
      expect(voter.lockedTokens).to.equal(LOCK_AMOUNT);
    });

    it("should revert if lock amount is zero", async function () {
      await gaiaToken.connect(voter1).approve(convictionVoting.getAddress(), LOCK_AMOUNT);

      await expect(
        convictionVoting.connect(voter1).lockTokens(0n)
      ).to.be.reverted;
    });

    it("should track totalLockedTokens", async function () {
      await gaiaToken.connect(voter1).approve(convictionVoting.getAddress(), LOCK_AMOUNT);
      await convictionVoting.connect(voter1).lockTokens(LOCK_AMOUNT);

      expect(await convictionVoting.totalLockedTokens()).to.equal(LOCK_AMOUNT);
    });

    it("should allow multiple locks from same voter", async function () {
      await gaiaToken.connect(voter1).approve(convictionVoting.getAddress(), LOCK_AMOUNT * 2n);
      await convictionVoting.connect(voter1).lockTokens(LOCK_AMOUNT);

      const balanceBefore = await convictionVoting.voterStates(voter1.address);
      expect(balanceBefore.lockedTokens).to.equal(LOCK_AMOUNT);

      await convictionVoting.connect(voter1).lockTokens(LOCK_AMOUNT);

      const balanceAfter = await convictionVoting.voterStates(voter1.address);
      expect(balanceAfter.lockedTokens).to.equal(LOCK_AMOUNT * 2n);
    });
  });

  describe("Token Unlocking", function () {
    beforeEach(async function () {
      await gaiaToken.connect(voter1).approve(convictionVoting.getAddress(), LOCK_AMOUNT);
      await convictionVoting.connect(voter1).lockTokens(LOCK_AMOUNT);
    });

    it("should unlock tokens", async function () {
      await expect(
        convictionVoting.connect(voter1).unlockTokens(LOCK_AMOUNT / 2n)
      ).to.emit(convictionVoting, "TokensUnlocked")
        .withArgs(voter1.address, LOCK_AMOUNT / 2n);

      const voter = await convictionVoting.voterStates(voter1.address);
      expect(voter.lockedTokens).to.equal(LOCK_AMOUNT / 2n);
    });

    it("should revert if unlocking while voting", async function () {
      await convictionVoting.connect(voter1).createProposal(
        0, // PARAMETER_CHANGE
        "Test Proposal",
        "Test Description",
        targetContract.address,
        "0x"
      );

      await convictionVoting.connect(voter1).allocateConviction(1);

      await expect(
        convictionVoting.connect(voter1).unlockTokens(LOCK_AMOUNT / 2n)
      ).to.be.reverted;
    });

    it("should revert if insufficient locked tokens", async function () {
      await expect(
        convictionVoting.connect(voter1).unlockTokens(LOCK_AMOUNT * 2n)
      ).to.be.reverted;
    });

    it("should update totalLockedTokens", async function () {
      await convictionVoting.connect(voter1).unlockTokens(LOCK_AMOUNT / 2n);

      expect(await convictionVoting.totalLockedTokens()).to.equal(LOCK_AMOUNT / 2n);
    });
  });

  describe("Proposal Creation", function () {
    beforeEach(async function () {
      await gaiaToken.connect(voter1).approve(convictionVoting.getAddress(), LOCK_AMOUNT);
      await convictionVoting.connect(voter1).lockTokens(LOCK_AMOUNT);
    });

    it("should create PARAMETER_CHANGE proposal", async function () {
      await expect(
        convictionVoting.connect(voter1).createProposal(
          0, // PARAMETER_CHANGE
          "Adjust Burn Rate",
          "Proposal to adjust burn rate from 5% to 3%",
          targetContract.address,
          "0x"
        )
      ).to.emit(convictionVoting, "ProposalCreated");

      const proposal = await convictionVoting.proposals(1);
      expect(proposal.proposer).to.equal(voter1.address);
      expect(proposal.title).to.equal("Adjust Burn Rate");
    });

    it("should create ORACLE_UPDATE proposal with 90% quorum", async function () {
      await expect(
        convictionVoting.connect(voter1).createProposal(
          2, // ORACLE_UPDATE
          "Update Oracle",
          "Proposal to update oracle model",
          targetContract.address,
          "0x"
        )
      ).to.emit(convictionVoting, "ProposalCreated");

      const proposal = await convictionVoting.proposals(1);
      const maxConviction = LOCK_AMOUNT * MAX_CONVICTION_PER_TOKEN;
      const expectedRequired = (maxConviction * ORACLE_QUORUM_BPS) / 10000n;
      expect(proposal.requiredConviction).to.equal(expectedRequired);
    });

    it("should create EMERGENCY_PAUSE proposal with 75% quorum", async function () {
      await expect(
        convictionVoting.connect(voter1).createProposal(
          3, // EMERGENCY_PAUSE
          "Pause Protocol",
          "Emergency protocol pause",
          targetContract.address,
          "0x"
        )
      ).to.emit(convictionVoting, "ProposalCreated");

      const proposal = await convictionVoting.proposals(1);
      const maxConviction = LOCK_AMOUNT * MAX_CONVICTION_PER_TOKEN;
      const expectedRequired = (maxConviction * EMERGENCY_QUORUM_BPS) / 10000n;
      expect(proposal.requiredConviction).to.equal(expectedRequired);
    });

    it("should revert if no tokens locked", async function () {
      await expect(
        convictionVoting.connect(voter2).createProposal(
          0,
          "Test",
          "Test",
          targetContract.address,
          "0x"
        )
      ).to.be.reverted;
    });

    it("should revert if empty title", async function () {
      await expect(
        convictionVoting.connect(voter1).createProposal(
          0,
          "",
          "Description",
          targetContract.address,
          "0x"
        )
      ).to.be.reverted;
    });

    it("should calculate correct quorum for standard proposals", async function () {
      await convictionVoting.connect(voter1).createProposal(
        0, // PARAMETER_CHANGE
        "Test",
        "Test",
        targetContract.address,
        "0x"
      );

      const proposal = await convictionVoting.proposals(1);
      const maxConviction = LOCK_AMOUNT * MAX_CONVICTION_PER_TOKEN;
      const expectedRequired = (maxConviction * STANDARD_QUORUM_BPS) / 10000n;
      expect(proposal.requiredConviction).to.equal(expectedRequired);
    });
  });

  describe("Conviction Allocation", function () {
    beforeEach(async function () {
      await gaiaToken.connect(voter1).approve(convictionVoting.getAddress(), LOCK_AMOUNT);
      await convictionVoting.connect(voter1).lockTokens(LOCK_AMOUNT);

      await convictionVoting.connect(voter1).createProposal(
        0,
        "Test Proposal",
        "Test",
        targetContract.address,
        "0x"
      );
    });

    it("should allocate conviction to proposal", async function () {
      await expect(
        convictionVoting.connect(voter1).allocateConviction(1)
      ).to.emit(convictionVoting, "ConvictionUpdated");

      const voter = await convictionVoting.voterStates(voter1.address);
      expect(voter.votedProposal).to.equal(1n);
    });

    it("should revert if not active proposal", async function () {
      // Create and immediately try to vote on non-existent proposal
      await expect(
        convictionVoting.connect(voter1).allocateConviction(999)
      ).to.be.reverted;
    });

    it("should revert if voting on different proposal", async function () {
      await convictionVoting.connect(voter1).allocateConviction(1);

      await convictionVoting.connect(voter1).createProposal(
        0,
        "Second Proposal",
        "Test",
        targetContract.address,
        "0x"
      );

      await expect(
        convictionVoting.connect(voter1).allocateConviction(2)
      ).to.be.revertedWithCustomError(convictionVoting, "AlreadyVotingOnDifferentProposal");
    });

    it("should accumulate conviction over blocks", async function () {
      await convictionVoting.connect(voter1).allocateConviction(1);

      const voterBefore = await convictionVoting.voterStates(voter1.address);
      const proposal1 = await convictionVoting.proposals(1);
      const conviction1 = proposal1.totalConviction;

      // Advance some blocks
      for (let i = 0; i < 10; i++) {
        await time.mine(1);
      }

      await convictionVoting.connect(voter1).allocateConviction(1);
      const proposal2 = await convictionVoting.proposals(1);
      const conviction2 = proposal2.totalConviction;

      expect(conviction2).to.be.greaterThan(conviction1);
    });
  });

  describe("Conviction Withdrawal", function () {
    beforeEach(async function () {
      await gaiaToken.connect(voter1).approve(convictionVoting.getAddress(), LOCK_AMOUNT);
      await convictionVoting.connect(voter1).lockTokens(LOCK_AMOUNT);

      await convictionVoting.connect(voter1).createProposal(
        0,
        "Test",
        "Test",
        targetContract.address,
        "0x"
      );

      await convictionVoting.connect(voter1).allocateConviction(1);
    });

    it("should withdraw conviction", async function () {
      const proposalBefore = await convictionVoting.proposals(1);
      const convictionBefore = proposalBefore.totalConviction;

      await convictionVoting.connect(voter1).withdrawConviction(1);

      const proposalAfter = await convictionVoting.proposals(1);
      const convictionAfter = proposalAfter.totalConviction;

      expect(convictionAfter).to.be.lessThan(convictionBefore);

      const voter = await convictionVoting.voterStates(voter1.address);
      expect(voter.votedProposal).to.equal(0n);
    });
  });

  describe("Proposal Execution", function () {
    beforeEach(async function () {
      // Setup multiple voters with tokens
      await gaiaToken.connect(voter1).approve(convictionVoting.getAddress(), LOCK_AMOUNT * 2n);
      await convictionVoting.connect(voter1).lockTokens(LOCK_AMOUNT * 2n);

      // Create and allocate conviction to reach quorum
      await convictionVoting.connect(voter1).createProposal(
        0,
        "Test Execution",
        "Test",
        targetContract.address,
        "0x"
      );

      // Allocate enough conviction
      await convictionVoting.connect(voter1).allocateConviction(1);
      for (let i = 0; i < 100; i++) {
        await time.mine(1);
      }
      await convictionVoting.connect(voter1).allocateConviction(1);
    });

    it("should revert if proposal not passed", async function () {
      await convictionVoting.connect(voter1).createProposal(
        0,
        "Failing Proposal",
        "Test",
        targetContract.address,
        "0x"
      );

      await expect(
        convictionVoting.connect(voter1).executeProposal(2)
      ).to.be.revertedWithCustomError(convictionVoting, "ProposalNotPassed");
    });

    it("should revert if not enough blocks have passed", async function () {
      const proposal = await convictionVoting.proposals(1);
      expect(proposal.status).to.equal(1); // PASSED

      // Try to execute before MIN_CONVICTION_BLOCKS
      await expect(
        convictionVoting.connect(voter1).executeProposal(1)
      ).to.be.revertedWithCustomError(convictionVoting, "ConvictionNotMature");
    });

    it("should execute after MIN_CONVICTION_BLOCKS", async function () {
      const proposal = await convictionVoting.proposals(1);
      expect(proposal.status).to.equal(1); // PASSED

      // Advance enough blocks
      for (let i = 0; i < 40400; i++) {
        await time.mine(1);
      }

      await expect(
        convictionVoting.connect(voter1).executeProposal(1)
      ).to.emit(convictionVoting, "ProposalExecuted");

      const executed = await convictionVoting.proposals(1);
      expect(executed.executed).to.be.true;
    });
  });

  describe("getVoterConviction", function () {
    it("should return 0 for non-voter", async function () {
      const conviction = await convictionVoting.getVoterConviction(voter1.address);
      expect(conviction).to.equal(0n);
    });

    it("should return conviction for voter", async function () {
      await gaiaToken.connect(voter1).approve(convictionVoting.getAddress(), LOCK_AMOUNT);
      await convictionVoting.connect(voter1).lockTokens(LOCK_AMOUNT);

      const conviction = await convictionVoting.getVoterConviction(voter1.address);
      expect(conviction).to.be.greaterThan(0n);
    });
  });

  describe("getProposalProgress", function () {
    beforeEach(async function () {
      await gaiaToken.connect(voter1).approve(convictionVoting.getAddress(), LOCK_AMOUNT);
      await convictionVoting.connect(voter1).lockTokens(LOCK_AMOUNT);

      await convictionVoting.connect(voter1).createProposal(
        0,
        "Progress Test",
        "Test",
        targetContract.address,
        "0x"
      );
    });

    it("should return proposal progress", async function () {
      const progress = await convictionVoting.getProposalProgress(1);

      expect(progress.required).to.be.greaterThan(0n);
      expect(progress.current).to.be.greaterThanOrEqual(0n);
    });
  });

  describe("Constants", function () {
    it("should have STANDARD_QUORUM_BPS = 33%", async function () {
      expect(await convictionVoting.STANDARD_QUORUM_BPS()).to.equal(STANDARD_QUORUM_BPS);
    });

    it("should have EMERGENCY_QUORUM_BPS = 75%", async function () {
      expect(await convictionVoting.EMERGENCY_QUORUM_BPS()).to.equal(EMERGENCY_QUORUM_BPS);
    });

    it("should have ORACLE_QUORUM_BPS = 90%", async function () {
      expect(await convictionVoting.ORACLE_QUORUM_BPS()).to.equal(ORACLE_QUORUM_BPS);
    });

    it("should have MIN_CONVICTION_BLOCKS = ~7 days", async function () {
      expect(await convictionVoting.MIN_CONVICTION_BLOCKS()).to.equal(MIN_CONVICTION_BLOCKS);
    });
  });
});
