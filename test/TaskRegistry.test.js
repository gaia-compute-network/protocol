const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("TaskRegistry", function () {
  let taskRegistry, gaiaToken, frozenOracle, validationPool, rewardDistributor;
  let owner, requester, miner1, miner2, miner3;

  const TASK_HASH = ethers.id("task_input_matrix");
  const JOB_TYPE_ID = ethers.id("species_identification");
  const INITIAL_REWARD = ethers.parseEther("1000");
  const BURN_RATE_BPS = 500n; // 5%
  const MIN_REWARD = ethers.parseEther("10");

  beforeEach(async function () {
    [owner, requester, miner1, miner2, miner3] = await ethers.getSigners();

    // Deploy GAIAToken
    const GAIAToken = await ethers.getContractFactory("GAIAToken");
    gaiaToken = await GAIAToken.deploy(owner.address);

    // Deploy FrozenOracle mock
    const MockConvictionVoting = await ethers.getContractFactory("MockConvictionVoting");
    const convictionVoting = await MockConvictionVoting.deploy();

    const FrozenOracle = await ethers.getContractFactory("FrozenOracle");
    frozenOracle = await FrozenOracle.deploy(convictionVoting.getAddress());
    await frozenOracle.initializeOracle(ethers.id("model"), "QmXxx");

    // Deploy mock ValidationPool and RewardDistributor
    const MockValidationPool = await ethers.getContractFactory("MockValidationPool");
    validationPool = await MockValidationPool.deploy();

    const MockRewardDistributor = await ethers.getContractFactory("MockRewardDistributor");
    rewardDistributor = await MockRewardDistributor.deploy();

    const TaskRegistry = await ethers.getContractFactory("TaskRegistry");
    taskRegistry = await TaskRegistry.deploy(
      gaiaToken.getAddress(),
      frozenOracle.getAddress(),
      validationPool.getAddress(),
      rewardDistributor.getAddress()
    );

    // Give requester tokens
    await gaiaToken.transfer(requester.address, ethers.parseEther("100000"));
    await gaiaToken.connect(requester).approve(taskRegistry.getAddress(), ethers.parseEther("100000"));
  });

  describe("Task Submission", function () {
    it("should submit task and burn 5%", async function () {
      const burnAmount = (INITIAL_REWARD * BURN_RATE_BPS) / 10000n;
      const escrowed = INITIAL_REWARD - burnAmount;

      await expect(
        taskRegistry.connect(requester).submitTask(
          TASK_HASH,
          JOB_TYPE_ID,
          INITIAL_REWARD,
          "USA",
          ethers.ZeroHash,
          3
        )
      ).to.emit(taskRegistry, "TaskSubmitted")
        .withArgs(1, requester.address, JOB_TYPE_ID, escrowed, burnAmount);

      expect(await taskRegistry.totalTokensBurned()).to.equal(burnAmount);
      expect(await taskRegistry.totalTasksSubmitted()).to.equal(1n);
    });

    it("should revert if reward is below minimum", async function () {
      const tinyReward = ethers.parseEther("1");

      await expect(
        taskRegistry.connect(requester).submitTask(
          TASK_HASH,
          JOB_TYPE_ID,
          tinyReward,
          "USA",
          ethers.ZeroHash,
          3
        )
      ).to.be.revertedWithCustomError(taskRegistry, "InsufficientReward");
    });

    it("should revert if job type not approved", async function () {
      const unapprovedJobType = ethers.id("financial_model_inference");

      await expect(
        taskRegistry.connect(requester).submitTask(
          TASK_HASH,
          unapprovedJobType,
          INITIAL_REWARD,
          "USA",
          ethers.ZeroHash,
          3
        )
      ).to.be.revertedWithCustomError(taskRegistry, "JobTypeNotApproved");
    });

    it("should set task status to PENDING", async function () {
      await taskRegistry.connect(requester).submitTask(
        TASK_HASH,
        JOB_TYPE_ID,
        INITIAL_REWARD,
        "USA",
        ethers.ZeroHash,
        3
      );

      const task = await taskRegistry.getTask(1);
      expect(task.status).to.equal(0); // PENDING
    });

    it("should store metadata correctly", async function () {
      const metadataEncrypted = ethers.id("encrypted_metadata");

      await taskRegistry.connect(requester).submitTask(
        TASK_HASH,
        JOB_TYPE_ID,
        INITIAL_REWARD,
        "KEN",
        metadataEncrypted,
        3
      );

      const task = await taskRegistry.getTask(1);
      expect(task.metadataCountry).to.equal("KEN");
      expect(task.metadataEncrypted).to.equal(metadataEncrypted);
    });
  });

  describe("Miner Assignment", function () {
    beforeEach(async function () {
      await taskRegistry.connect(requester).submitTask(
        TASK_HASH,
        JOB_TYPE_ID,
        INITIAL_REWARD,
        "USA",
        ethers.ZeroHash,
        3
      );
    });

    it("should assign miners by validationPool", async function () {
      const miners = [miner1.address, miner2.address, miner3.address];

      await expect(
        validationPool.assignMiners(taskRegistry.getAddress(), 1, miners)
      ).to.emit(taskRegistry, "MinersAssigned")
        .withArgs(1, miners);

      const task = await taskRegistry.getTask(1);
      expect(task.status).to.equal(1); // ASSIGNED
      expect(task.assignedMiners.length).to.equal(3);
    });

    it("should revert if not validationPool", async function () {
      const miners = [miner1.address, miner2.address, miner3.address];

      await expect(
        taskRegistry.assignMiners(1, miners)
      ).to.be.revertedWithCustomError(taskRegistry, "NotValidationPool");
    });
  });

  describe("Result Submission", function () {
    beforeEach(async function () {
      await taskRegistry.connect(requester).submitTask(
        TASK_HASH,
        JOB_TYPE_ID,
        INITIAL_REWARD,
        "USA",
        ethers.ZeroHash,
        3
      );

      const miners = [miner1.address, miner2.address, miner3.address];
      await validationPool.assignMiners(taskRegistry.getAddress(), 1, miners);
    });

    it("should submit result with fingerprint", async function () {
      const resultHash = ethers.id("result_matrix");
      const commitment = ethers.id("commitment_proof");
      const resultFingerprint = ethers.id("species_id_result");

      await expect(
        taskRegistry.connect(miner1).submitResult(
          1,
          resultHash,
          commitment,
          resultFingerprint
        )
      ).to.emit(taskRegistry, "ResultSubmitted")
        .withArgs(1, miner1.address, resultFingerprint);

      const submissions = await taskRegistry.getSubmissions(1);
      expect(submissions.length).to.equal(1);
      expect(submissions[0].resultFingerprint).to.equal(resultFingerprint);
    });

    it("should revert if miner not assigned", async function () {
      const resultHash = ethers.id("result");
      const commitment = ethers.id("commitment");
      const fingerprint = ethers.id("fingerprint");

      const otherAccount = (await ethers.getSigners())[4];

      await expect(
        taskRegistry.connect(otherAccount).submitResult(1, resultHash, commitment, fingerprint)
      ).to.be.revertedWithCustomError(taskRegistry, "NotAssignedMiner");
    });

    it("should revert if miner already submitted", async function () {
      const resultHash = ethers.id("result");
      const commitment = ethers.id("commitment");
      const fingerprint = ethers.id("fingerprint");

      await taskRegistry.connect(miner1).submitResult(1, resultHash, commitment, fingerprint);

      await expect(
        taskRegistry.connect(miner1).submitResult(1, resultHash, commitment, fingerprint)
      ).to.be.revertedWithCustomError(taskRegistry, "AlreadySubmitted");
    });

    it("should transition to VALIDATING when all miners submit", async function () {
      const resultHash = ethers.id("result");
      const commitment = ethers.id("commitment");
      const fingerprint = ethers.id("fingerprint");

      await taskRegistry.connect(miner1).submitResult(1, resultHash, commitment, fingerprint);
      await taskRegistry.connect(miner2).submitResult(1, resultHash, commitment, fingerprint);

      let task = await taskRegistry.getTask(1);
      expect(task.status).to.equal(2); // COMPUTING

      await taskRegistry.connect(miner3).submitResult(1, resultHash, commitment, fingerprint);

      task = await taskRegistry.getTask(1);
      expect(task.status).to.equal(3); // VALIDATING
    });
  });

  describe("Task Verification", function () {
    beforeEach(async function () {
      await taskRegistry.connect(requester).submitTask(
        TASK_HASH,
        JOB_TYPE_ID,
        INITIAL_REWARD,
        "USA",
        ethers.ZeroHash,
        3
      );

      const miners = [miner1.address, miner2.address, miner3.address];
      await validationPool.assignMiners(taskRegistry.getAddress(), 1, miners);

      const resultFingerprint = ethers.id("agreed_result");
      await taskRegistry.connect(miner1).submitResult(
        1,
        ethers.id("result1"),
        ethers.id("commitment1"),
        resultFingerprint
      );
      await taskRegistry.connect(miner2).submitResult(
        1,
        ethers.id("result2"),
        ethers.id("commitment2"),
        resultFingerprint
      );
      await taskRegistry.connect(miner3).submitResult(
        1,
        ethers.id("result3"),
        ethers.id("commitment3"),
        resultFingerprint
      );
    });

    it("should finalize verified task", async function () {
      const agreedFingerprint = ethers.id("agreed_result");

      await expect(
        validationPool.finalizeTaskVerified(
          taskRegistry.getAddress(),
          1,
          agreedFingerprint,
          []
        )
      ).to.emit(taskRegistry, "TaskVerified");

      const task = await taskRegistry.getTask(1);
      expect(task.status).to.equal(4); // VERIFIED
      expect(task.agreedFingerprint).to.equal(agreedFingerprint);
    });

    it("should track slashed miners", async function () {
      const agreedFingerprint = ethers.id("agreed_result");

      await validationPool.finalizeTaskVerified(
        taskRegistry.getAddress(),
        1,
        agreedFingerprint,
        [miner3.address]
      );

      const submissions = await taskRegistry.getSubmissions(1);
      expect(submissions[2].slashed).to.be.true;
      expect(submissions[0].slashed).to.be.false;
    });

    it("should increment totalTasksVerified", async function () {
      const agreedFingerprint = ethers.id("agreed_result");

      await validationPool.finalizeTaskVerified(
        taskRegistry.getAddress(),
        1,
        agreedFingerprint,
        []
      );

      expect(await taskRegistry.totalTasksVerified()).to.equal(1n);
    });
  });

  describe("isReadyForValidation", function () {
    it("should return false for non-validating task", async function () {
      await taskRegistry.connect(requester).submitTask(
        TASK_HASH,
        JOB_TYPE_ID,
        INITIAL_REWARD,
        "USA",
        ethers.ZeroHash,
        3
      );

      expect(await taskRegistry.isReadyForValidation(1)).to.be.false;
    });

    it("should return true for VALIDATING task", async function () {
      await taskRegistry.connect(requester).submitTask(
        TASK_HASH,
        JOB_TYPE_ID,
        INITIAL_REWARD,
        "USA",
        ethers.ZeroHash,
        3
      );

      const miners = [miner1.address, miner2.address, miner3.address];
      await validationPool.assignMiners(taskRegistry.getAddress(), 1, miners);

      const resultFingerprint = ethers.id("result");
      await taskRegistry.connect(miner1).submitResult(1, ethers.id("r1"), ethers.id("c1"), resultFingerprint);
      await taskRegistry.connect(miner2).submitResult(1, ethers.id("r2"), ethers.id("c2"), resultFingerprint);
      await taskRegistry.connect(miner3).submitResult(1, ethers.id("r3"), ethers.id("c3"), resultFingerprint);

      expect(await taskRegistry.isReadyForValidation(1)).to.be.true;
    });
  });

  describe("View Functions", function () {
    it("should get task details", async function () {
      await taskRegistry.connect(requester).submitTask(
        TASK_HASH,
        JOB_TYPE_ID,
        INITIAL_REWARD,
        "USA",
        ethers.ZeroHash,
        3
      );

      const task = await taskRegistry.getTask(1);
      expect(task.taskId).to.equal(1n);
      expect(task.requester).to.equal(requester.address);
      expect(task.taskHash).to.equal(TASK_HASH);
    });

    it("should get task reward", async function () {
      await taskRegistry.connect(requester).submitTask(
        TASK_HASH,
        JOB_TYPE_ID,
        INITIAL_REWARD,
        "USA",
        ethers.ZeroHash,
        3
      );

      const reward = await taskRegistry.getTaskReward(1);
      const expectedReward = INITIAL_REWARD - (INITIAL_REWARD * BURN_RATE_BPS) / 10000n;
      expect(reward).to.equal(expectedReward);
    });
  });
});
