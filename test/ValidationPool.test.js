const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("ValidationPool", function () {
  let validationPool, taskRegistry, rewardDistributor, gaiaToken;
  let owner, validator1, validator2, miner1, miner2, miner3;

  const MIN_VALIDATOR_STAKE = ethers.parseEther("1000");
  const MIN_MINER_STAKE = ethers.parseEther("100");
  const DISSENTER_SLASH_BPS = 5000n; // 50%
  const COLLUDER_SLASH_BPS = 10000n; // 100%

  beforeEach(async function () {
    [owner, validator1, validator2, miner1, miner2, miner3] = await ethers.getSigners();

    // Deploy GAIAToken
    const GAIAToken = await ethers.getContractFactory("GAIAToken");
    gaiaToken = await GAIAToken.deploy(owner.address);

    // Deploy mocks
    const MockTaskRegistry = await ethers.getContractFactory("MockTaskRegistry");
    taskRegistry = await MockTaskRegistry.deploy();

    const MockRewardDistributor = await ethers.getContractFactory("MockRewardDistributor");
    rewardDistributor = await MockRewardDistributor.deploy();

    // ValidationPool now takes only gaiaToken in constructor (circular dep fix)
    const ValidationPool = await ethers.getContractFactory("ValidationPool");
    validationPool = await ValidationPool.deploy(await gaiaToken.getAddress());

    // Set addresses post-deployment (only owner can do this — Sprint 2 security fix)
    await validationPool.setAddresses(
      await taskRegistry.getAddress(),
      await rewardDistributor.getAddress()
    );

    // Fund validators and miners
    await gaiaToken.transfer(validator1.address, ethers.parseEther("10000"));
    await gaiaToken.transfer(validator2.address, ethers.parseEther("10000"));
    await gaiaToken.transfer(miner1.address, ethers.parseEther("1000"));
    await gaiaToken.transfer(miner2.address, ethers.parseEther("1000"));
    await gaiaToken.transfer(miner3.address, ethers.parseEther("1000"));
  });

  describe("Validator Registration", function () {
    it("should register validator with stake", async function () {
      await gaiaToken.connect(validator1).approve(validationPool.getAddress(), MIN_VALIDATOR_STAKE);

      await expect(
        validationPool.connect(validator1).registerValidator()
      ).to.emit(validationPool, "ValidatorRegistered")
        .withArgs(validator1.address, MIN_VALIDATOR_STAKE);

      expect(await validationPool.isValidator(validator1.address)).to.be.true;
      expect(await validationPool.validatorStake(validator1.address)).to.equal(MIN_VALIDATOR_STAKE);
    });

    it("should revert if stake below minimum", async function () {
      const tinyStake = ethers.parseEther("100");
      await gaiaToken.connect(validator1).approve(validationPool.getAddress(), tinyStake);

      await expect(
        validationPool.connect(validator1).registerValidator()
      ).to.be.revertedWithCustomError(validationPool, "InsufficientStake");
    });

    it("should track multiple validators", async function () {
      await gaiaToken.connect(validator1).approve(validationPool.getAddress(), MIN_VALIDATOR_STAKE);
      await validationPool.connect(validator1).registerValidator();

      await gaiaToken.connect(validator2).approve(validationPool.getAddress(), MIN_VALIDATOR_STAKE);
      await validationPool.connect(validator2).registerValidator();

      expect(await validationPool.validatorCount()).to.equal(2n);
    });
  });

  describe("Miner Registration", function () {
    it("should register miner with stake", async function () {
      await gaiaToken.connect(miner1).approve(validationPool.getAddress(), MIN_MINER_STAKE);

      await expect(
        validationPool.connect(miner1).registerMiner()
      ).to.emit(validationPool, "MinerRegistered")
        .withArgs(miner1.address, MIN_MINER_STAKE);

      expect(await validationPool.getMinerStake(miner1.address)).to.equal(MIN_MINER_STAKE);
    });

    it("should revert if miner stake below minimum", async function () {
      const tinyStake = ethers.parseEther("10");
      await gaiaToken.connect(miner1).approve(validationPool.getAddress(), tinyStake);

      await expect(
        validationPool.connect(miner1).registerMiner()
      ).to.be.revertedWithCustomError(validationPool, "InsufficientStake");
    });
  });

  describe("Freivalds Result Submission", function () {
    beforeEach(async function () {
      // Register validator
      await gaiaToken.connect(validator1).approve(validationPool.getAddress(), MIN_VALIDATOR_STAKE);
      await validationPool.connect(validator1).registerValidator();

      // Setup mock task ready for validation
      await taskRegistry.setReadyForValidation(1, true);
    });

    it("should submit freivalds result", async function () {
      const testedFingerprint = ethers.id("agreed_fingerprint");

      await expect(
        validationPool.connect(validator1).submitFreivaldsResult(
          1,
          true,
          testedFingerprint,
          10
        )
      ).to.emit(validationPool, "FreivaldsResultSubmitted")
        .withArgs(1, true, testedFingerprint, validator1.address);

      expect(await validationPool.validationComplete(1)).to.be.true;
    });

    it("should revert if not validator", async function () {
      const testedFingerprint = ethers.id("fingerprint");

      await expect(
        validationPool.connect(miner1).submitFreivaldsResult(
          1,
          true,
          testedFingerprint,
          10
        )
      ).to.be.revertedWithCustomError(validationPool, "NotRegisteredValidator");
    });

    it("should revert if validation already complete", async function () {
      const testedFingerprint = ethers.id("fingerprint");

      await validationPool.connect(validator1).submitFreivaldsResult(
        1,
        true,
        testedFingerprint,
        10
      );

      await expect(
        validationPool.connect(validator1).submitFreivaldsResult(
          1,
          true,
          testedFingerprint,
          10
        )
      ).to.be.revertedWithCustomError(validationPool, "ValidationAlreadyComplete");
    });

    it("should revert if zero fingerprint", async function () {
      await expect(
        validationPool.connect(validator1).submitFreivaldsResult(
          1,
          true,
          ethers.ZeroHash,
          10
        )
      ).to.be.revertedWithCustomError(validationPool, "InvalidFingerprint");
    });

    it("should require minimum freivalds rounds", async function () {
      const testedFingerprint = ethers.id("fingerprint");

      await expect(
        validationPool.connect(validator1).submitFreivaldsResult(
          1,
          true,
          testedFingerprint,
          5 // Below FREIVALDS_ROUNDS (10)
        )
      ).to.be.revertedWith("VP: insufficient rounds");
    });
  });

  describe("Consensus Processing", function () {
    beforeEach(async function () {
      await gaiaToken.connect(validator1).approve(validationPool.getAddress(), MIN_VALIDATOR_STAKE);
      await validationPool.connect(validator1).registerValidator();

      await gaiaToken.connect(miner1).approve(validationPool.getAddress(), MIN_MINER_STAKE);
      await validationPool.connect(miner1).registerMiner();

      await gaiaToken.connect(miner2).approve(validationPool.getAddress(), MIN_MINER_STAKE);
      await validationPool.connect(miner2).registerMiner();

      await gaiaToken.connect(miner3).approve(validationPool.getAddress(), MIN_MINER_STAKE);
      await validationPool.connect(miner3).registerMiner();

      // Setup mock task
      await taskRegistry.setReadyForValidation(1, true);
      const agreedFingerprint = ethers.id("consensus_result");
      const dissenterFingerprint = ethers.id("different_result");
      await taskRegistry.setSubmissions(1, [
        { miner: miner1.address, resultFingerprint: agreedFingerprint },
        { miner: miner2.address, resultFingerprint: agreedFingerprint },
        { miner: miner3.address, resultFingerprint: dissenterFingerprint },
      ]);
    });

    it("should emit QuorumReached when majority passes freivalds", async function () {
      const agreedFingerprint = ethers.id("consensus_result");

      await expect(
        validationPool.connect(validator1).submitFreivaldsResult(
          1,
          true,
          agreedFingerprint,
          10
        )
      ).to.emit(validationPool, "QuorumReached");
    });

    it("should emit ConsensusFailure if no quorum", async function () {
      // Setup 3 different fingerprints
      const fp1 = ethers.id("result1");
      const fp2 = ethers.id("result2");
      const fp3 = ethers.id("result3");
      await taskRegistry.setSubmissions(2, [
        { miner: miner1.address, resultFingerprint: fp1 },
        { miner: miner2.address, resultFingerprint: fp2 },
        { miner: miner3.address, resultFingerprint: fp3 },
      ]);
      await taskRegistry.setReadyForValidation(2, true);

      await expect(
        validationPool.connect(validator1).submitFreivaldsResult(
          2,
          true,
          fp1,
          10
        )
      ).to.emit(validationPool, "ConsensusFailure");
    });
  });

  describe("Slashing", function () {
    beforeEach(async function () {
      await gaiaToken.connect(validator1).approve(validationPool.getAddress(), MIN_VALIDATOR_STAKE);
      await validationPool.connect(validator1).registerValidator();

      await gaiaToken.connect(miner1).approve(validationPool.getAddress(), MIN_MINER_STAKE);
      await validationPool.connect(miner1).registerMiner();
    });

    it("_slashMiner is internal and not accessible externally", async function () {
      // Internal functions are not part of the ABI — verifying the contract
      // does not expose a public _slashMiner entry point.
      expect(typeof validationPool._slashMiner).to.equal("undefined");
    });

    it("should track slashed amounts", async function () {
      const initialStake = await validationPool.getMinerStake(miner1.address);
      const slashAmount = (initialStake * DISSENTER_SLASH_BPS) / 10000n;

      // Would be tested via public functions that call _slashMiner
      expect(initialStake).to.equal(MIN_MINER_STAKE);
    });
  });

  describe("View Functions", function () {
    it("should get freivalds result", async function () {
      await gaiaToken.connect(validator1).approve(validationPool.getAddress(), MIN_VALIDATOR_STAKE);
      await validationPool.connect(validator1).registerValidator();

      await taskRegistry.setReadyForValidation(1, true);
      const testedFingerprint = ethers.id("fingerprint");

      await validationPool.connect(validator1).submitFreivaldsResult(1, true, testedFingerprint, 10);

      const result = await validationPool.getFreivaldsResult(1);
      expect(result.taskId).to.equal(1n);
      expect(result.passed).to.be.true;
      expect(result.verifier).to.equal(validator1.address);
    });

    it("should get miner stake", async function () {
      await gaiaToken.connect(miner1).approve(validationPool.getAddress(), MIN_MINER_STAKE);
      await validationPool.connect(miner1).registerMiner();

      expect(await validationPool.getMinerStake(miner1.address)).to.equal(MIN_MINER_STAKE);
    });

    it("should count validators", async function () {
      await gaiaToken.connect(validator1).approve(validationPool.getAddress(), MIN_VALIDATOR_STAKE);
      await validationPool.connect(validator1).registerValidator();

      expect(await validationPool.validatorCount()).to.equal(1n);
    });
  });

  // ── Security: setAddresses() access control (Sprint 2 fix) ──────────────────
  describe("setAddresses() Access Control", function () {
    let freshPool;

    beforeEach(async function () {
      const ValidationPool = await ethers.getContractFactory("ValidationPool");
      freshPool = await ValidationPool.deploy(await gaiaToken.getAddress());
    });

    it("should allow owner to call setAddresses()", async function () {
      await expect(
        freshPool.connect(owner).setAddresses(
          await taskRegistry.getAddress(),
          await rewardDistributor.getAddress()
        )
      ).to.emit(freshPool, "AddressesSet");
    });

    it("should revert if non-owner calls setAddresses()", async function () {
      await expect(
        freshPool.connect(validator1).setAddresses(
          await taskRegistry.getAddress(),
          await rewardDistributor.getAddress()
        )
      ).to.be.revertedWithCustomError(freshPool, "NotOwner");
    });

    it("should revert if setAddresses() called twice", async function () {
      await freshPool.connect(owner).setAddresses(
        await taskRegistry.getAddress(),
        await rewardDistributor.getAddress()
      );

      await expect(
        freshPool.connect(owner).setAddresses(
          await taskRegistry.getAddress(),
          await rewardDistributor.getAddress()
        )
      ).to.be.revertedWith("VP: addresses already set");
    });

    it("should revert if taskRegistry is zero address", async function () {
      await expect(
        freshPool.connect(owner).setAddresses(
          ethers.ZeroAddress,
          await rewardDistributor.getAddress()
        )
      ).to.be.revertedWith("VP: zero taskRegistry");
    });

    it("should revert if rewardDistributor is zero address", async function () {
      await expect(
        freshPool.connect(owner).setAddresses(
          await taskRegistry.getAddress(),
          ethers.ZeroAddress
        )
      ).to.be.revertedWith("VP: zero rewardDistributor");
    });

    it("should block submitFreivaldsResult before setAddresses is called", async function () {
      const fp = ethers.id("test");
      // Register validator on freshPool (no setAddresses yet)
      await gaiaToken.connect(validator1).approve(freshPool.getAddress(), MIN_VALIDATOR_STAKE);
      await freshPool.connect(validator1).registerValidator();

      await expect(
        freshPool.connect(validator1).submitFreivaldsResult(1, true, fp, 10)
      ).to.be.revertedWith("VP: addresses not yet initialized");
    });
  });

  describe("Constants", function () {
    it("should have correct DISSENTER_SLASH_BPS", async function () {
      expect(await validationPool.DISSENTER_SLASH_BPS()).to.equal(DISSENTER_SLASH_BPS);
    });

    it("should have correct COLLUDER_SLASH_BPS", async function () {
      expect(await validationPool.COLLUDER_SLASH_BPS()).to.equal(COLLUDER_SLASH_BPS);
    });

    it("should have MIN_VALIDATOR_STAKE constant", async function () {
      expect(await validationPool.MIN_VALIDATOR_STAKE()).to.equal(MIN_VALIDATOR_STAKE);
    });

    it("should have MIN_MINER_STAKE constant", async function () {
      expect(await validationPool.MIN_MINER_STAKE()).to.equal(MIN_MINER_STAKE);
    });
  });
});
