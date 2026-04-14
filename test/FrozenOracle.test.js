const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

describe("FrozenOracle", function () {
  let frozenOracle;
  let convictionVoting;
  let owner;

  const ORACLE_MODEL_HASH = ethers.id("oracle_model_weights_v1");
  const ORACLE_MODEL_CID = "QmXxxx";
  const ORACLE_UPDATE_PERIOD = 10n * 365n * 24n * 60n * 60n; // 10 years in seconds
  const ORACLE_UPDATE_QUORUM_BPS = 9000n;

  beforeEach(async function () {
    [owner] = await ethers.getSigners();

    // Deploy minimal ConvictionVoting mock
    const MockConvictionVoting = await ethers.getContractFactory("MockConvictionVoting");
    convictionVoting = await MockConvictionVoting.deploy();

    const FrozenOracle = await ethers.getContractFactory("FrozenOracle");
    frozenOracle = await FrozenOracle.deploy(convictionVoting.getAddress());
  });

  describe("Deployment", function () {
    it("should set convictionVoting address", async function () {
      expect(await frozenOracle.convictionVoting()).to.equal(
        convictionVoting.getAddress()
      );
    });

    it("should set genesisTimestamp", async function () {
      const genesisTs = await frozenOracle.genesisTimestamp();
      expect(genesisTs).to.be.greaterThan(0n);
    });

    it("should set nextUpdateWindow correctly", async function () {
      const genesis = await frozenOracle.genesisTimestamp();
      const nextWindow = await frozenOracle.nextUpdateWindow();
      expect(nextWindow).to.equal(genesis + ORACLE_UPDATE_PERIOD);
    });

    it("should have empty oracle model hash initially", async function () {
      expect(await frozenOracle.oracleModelHash()).to.equal(ethers.ZeroHash);
    });
  });

  describe("Oracle Initialization", function () {
    it("should initialize oracle with hash and CID", async function () {
      await expect(
        frozenOracle.initializeOracle(ORACLE_MODEL_HASH, ORACLE_MODEL_CID)
      ).to.emit(frozenOracle, "OracleInitialized")
        .withArgs(ORACLE_MODEL_HASH, ORACLE_MODEL_CID, await time.latest());

      expect(await frozenOracle.oracleModelHash()).to.equal(ORACLE_MODEL_HASH);
      expect(await frozenOracle.oracleModelCID()).to.equal(ORACLE_MODEL_CID);
    });

    it("should approve 9 default job types on initialization", async function () {
      await frozenOracle.initializeOracle(ORACLE_MODEL_HASH, ORACLE_MODEL_CID);

      const count = await frozenOracle.approvedJobTypeCount();
      expect(count).to.equal(9n);
    });

    it("should revert on double initialization", async function () {
      await frozenOracle.initializeOracle(ORACLE_MODEL_HASH, ORACLE_MODEL_CID);

      await expect(
        frozenOracle.initializeOracle(ORACLE_MODEL_HASH, ORACLE_MODEL_CID)
      ).to.be.revertedWithCustomError(frozenOracle, "OracleAlreadyInitialized");
    });

    it("should revert if hash is zero", async function () {
      await expect(
        frozenOracle.initializeOracle(ethers.ZeroHash, ORACLE_MODEL_CID)
      ).to.be.revertedWithCustomError(frozenOracle, "ZeroHash");
    });

    it("should approve species_identification job type", async function () {
      await frozenOracle.initializeOracle(ORACLE_MODEL_HASH, ORACLE_MODEL_CID);

      const jobTypeId = ethers.id("species_identification");
      expect(await frozenOracle.isApprovedJobType(jobTypeId)).to.be.true;
    });
  });

  describe("Job Type Validation", function () {
    beforeEach(async function () {
      await frozenOracle.initializeOracle(ORACLE_MODEL_HASH, ORACLE_MODEL_CID);
    });

    it("should allow approved job type via requireApproved", async function () {
      const jobTypeId = ethers.id("deforestation_detection");
      await expect(
        frozenOracle.requireApproved(jobTypeId)
      ).not.to.be.reverted;
    });

    it("should revert for unapproved job type via requireApproved", async function () {
      const unapprovedJobTypeId = ethers.id("unauthorized_job_type");
      await expect(
        frozenOracle.requireApproved(unapprovedJobTypeId)
      ).to.be.revertedWithCustomError(frozenOracle, "JobTypeNotApproved");
    });

    it("should return true for approved job type via isInScope", async function () {
      const jobTypeId = ethers.id("ocean_temperature_inference");
      expect(await frozenOracle.isInScope(jobTypeId)).to.be.true;
    });

    it("should return false for unapproved job type via isInScope", async function () {
      const unapprovedJobTypeId = ethers.id("financial_model_inference");
      expect(await frozenOracle.isInScope(unapprovedJobTypeId)).to.be.false;
    });

    it("should allow freivalds_demo for protocol testing", async function () {
      const demoJobTypeId = ethers.id("freivalds_demo");
      expect(await frozenOracle.isInScope(demoJobTypeId)).to.be.true;
    });
  });

  describe("Job Type ID Generation", function () {
    it("should compute jobTypeId correctly", async function () {
      const jobTypeName = "species_identification";
      const computed = await frozenOracle.jobTypeId(jobTypeName);
      const expected = ethers.id(jobTypeName);

      expect(computed).to.equal(expected);
    });
  });

  describe("Job Type Descriptions", function () {
    beforeEach(async function () {
      await frozenOracle.initializeOracle(ORACLE_MODEL_HASH, ORACLE_MODEL_CID);
    });

    it("should store and retrieve job type description", async function () {
      const jobTypeId = ethers.id("species_identification");
      const description = await frozenOracle.jobTypeDescription(jobTypeId);
      expect(description).to.include("Species identification");
    });

    it("should have description for carbon_sequestration", async function () {
      const jobTypeId = ethers.id("carbon_sequestration");
      const description = await frozenOracle.jobTypeDescription(jobTypeId);
      expect(description).to.include("LiDAR");
    });
  });

  describe("Oracle Update (governance)", function () {
    beforeEach(async function () {
      await frozenOracle.initializeOracle(ORACLE_MODEL_HASH, ORACLE_MODEL_CID);
    });

    it("should revert if not called by ConvictionVoting", async function () {
      const newHash = ethers.id("new_oracle_weights");
      const newCID = "QmYyyy";

      await expect(
        frozenOracle.executeOracleUpdate(newHash, newCID)
      ).to.be.revertedWithCustomError(frozenOracle, "NotConvictionVoting");
    });

    it("should revert if update window not open", async function () {
      const newHash = ethers.id("new_oracle_weights");
      const newCID = "QmYyyy";

      await expect(
        convictionVoting.executeOracleUpdate(frozenOracle.getAddress(), newHash, newCID)
      ).to.be.revertedWithCustomError(frozenOracle, "UpdateWindowNotOpen");
    });

    it("should execute update when called by ConvictionVoting in update window", async function () {
      const newHash = ethers.id("new_oracle_weights");
      const newCID = "QmYyyy";

      // Fast-forward to update window
      const nextWindow = await frozenOracle.nextUpdateWindow();
      await time.increaseTo(nextWindow);

      await expect(
        convictionVoting.executeOracleUpdate(frozenOracle.getAddress(), newHash, newCID)
      ).to.emit(frozenOracle, "OracleUpdated")
        .withArgs(ORACLE_MODEL_HASH, newHash, newCID);

      expect(await frozenOracle.oracleModelHash()).to.equal(newHash);
      expect(await frozenOracle.oracleModelCID()).to.equal(newCID);
    });

    it("should set nextUpdateWindow to 10 years after update", async function () {
      const newHash = ethers.id("new_oracle_weights");
      const newCID = "QmYyyy";

      const nextWindow = await frozenOracle.nextUpdateWindow();
      await time.increaseTo(nextWindow);

      const txBlock = await ethers.provider.getBlockNumber();
      const txTime = (await ethers.provider.getBlock(txBlock)).timestamp;

      await convictionVoting.executeOracleUpdate(frozenOracle.getAddress(), newHash, newCID);

      const newNextWindow = await frozenOracle.nextUpdateWindow();
      expect(newNextWindow).to.equal(BigInt(txTime) + ORACLE_UPDATE_PERIOD);
    });

    it("should revert if new hash is zero", async function () {
      const nextWindow = await frozenOracle.nextUpdateWindow();
      await time.increaseTo(nextWindow);

      await expect(
        convictionVoting.executeOracleUpdate(frozenOracle.getAddress(), ethers.ZeroHash, "QmYyyy")
      ).to.be.revertedWithCustomError(frozenOracle, "ZeroHash");
    });
  });

  describe("View Helpers", function () {
    beforeEach(async function () {
      await frozenOracle.initializeOracle(ORACLE_MODEL_HASH, ORACLE_MODEL_CID);
    });

    it("should return approvedJobTypeCount", async function () {
      const count = await frozenOracle.approvedJobTypeCount();
      expect(count).to.equal(9n);
    });

    it("should return years until next update window", async function () {
      const years = await frozenOracle.yearsUntilNextUpdateWindow();
      expect(years).to.equal(10n);
    });

    it("should return 0 years if update window is open", async function () {
      const nextWindow = await frozenOracle.nextUpdateWindow();
      await time.increaseTo(nextWindow);

      const years = await frozenOracle.yearsUntilNextUpdateWindow();
      expect(years).to.equal(0n);
    });
  });

  describe("Constants", function () {
    it("should have correct ORACLE_UPDATE_QUORUM_BPS", async function () {
      expect(await frozenOracle.ORACLE_UPDATE_QUORUM_BPS()).to.equal(ORACLE_UPDATE_QUORUM_BPS);
    });

    it("should have correct ORACLE_UPDATE_PERIOD", async function () {
      expect(await frozenOracle.ORACLE_UPDATE_PERIOD()).to.equal(ORACLE_UPDATE_PERIOD);
    });

    it("should have correct ORACLE_SPEC_VERSION", async function () {
      expect(await frozenOracle.ORACLE_SPEC_VERSION()).to.equal("gaia-oracle-v1.0");
    });
  });
});
