/**
 * GAIA Protocol — Hardhat Deployment Script
 *
 * Deploys all 8 contracts in the correct order and configures
 * the genesis state. Run with:
 *   npx hardhat run scripts/deploy.js --network <arbitrum-goerli|mainnet>
 *
 * Environment variables required:
 *   GENESIS_COORDINATOR_ADDRESS  — multi-sig of genesis ceremony participants
 *   PRIVATE_KEY                  — deployer private key (must be genesis coordinator)
 *   RPC_URL                      — node RPC endpoint
 *   ORACLE_MODEL_HASH            — bytes32 SHA-256 of oracle model weights
 *   ORACLE_MODEL_CID             — IPFS CID of oracle model
 */

const hre = require("hardhat");
const { ethers } = require("hardhat");

async function main() {
  const [deployer] = await ethers.getSigners();
  console.log("══════════════════════════════════════════════════════");
  console.log("  GAIA Protocol — Genesis Deployment");
  console.log("══════════════════════════════════════════════════════");
  console.log(`  Deployer:    ${deployer.address}`);
  console.log(`  Balance:     ${ethers.formatEther(await ethers.provider.getBalance(deployer.address))} ETH`);
  console.log(`  Network:     ${hre.network.name}`);
  console.log(`  Timestamp:   ${new Date().toISOString()}`);
  console.log("──────────────────────────────────────────────────────");

  const genesisCoordinator = process.env.GENESIS_COORDINATOR_ADDRESS || deployer.address;
  const oracleModelHash    = process.env.ORACLE_MODEL_HASH || ethers.keccak256(ethers.toUtf8Bytes("gaia-oracle-v1.0-placeholder"));
  const oracleModelCID     = process.env.ORACLE_MODEL_CID || "QmPlaceholderCIDReplaceBeforeMainnet";

  const deployed = {};

  // ── Step 1: Deploy GAIAToken ────────────────────────────────────────────────
  // Token deployed first with a placeholder receiver; will be updated to TimeLock
  // In production: deploy TimeLock first with a placeholder, then token
  console.log("\n[1/8] Deploying GAIAToken...");
  const GAIAToken = await ethers.getContractFactory("GAIAToken");
  // Temporary: mint to deployer, will transfer to TimeLock
  const gaiaToken = await GAIAToken.deploy(deployer.address);
  await gaiaToken.waitForDeployment();
  deployed.gaiaToken = await gaiaToken.getAddress();
  console.log(`      GAIAToken:          ${deployed.gaiaToken}`);
  console.log(`      Total supply:       ${ethers.formatEther(await gaiaToken.totalSupply())} GAIA`);

  // ── Step 2: Deploy ConvictionVoting ─────────────────────────────────────────
  console.log("\n[2/8] Deploying ConvictionVoting...");
  const ConvictionVoting = await ethers.getContractFactory("ConvictionVoting");
  const convictionVoting = await ConvictionVoting.deploy(deployed.gaiaToken);
  await convictionVoting.waitForDeployment();
  deployed.convictionVoting = await convictionVoting.getAddress();
  console.log(`      ConvictionVoting:   ${deployed.convictionVoting}`);

  // ── Step 3: Deploy FrozenOracle ─────────────────────────────────────────────
  console.log("\n[3/8] Deploying FrozenOracle...");
  const FrozenOracle = await ethers.getContractFactory("FrozenOracle");
  const frozenOracle = await FrozenOracle.deploy(deployed.convictionVoting);
  await frozenOracle.waitForDeployment();
  deployed.frozenOracle = await frozenOracle.getAddress();
  console.log(`      FrozenOracle:       ${deployed.frozenOracle}`);

  // ── Step 4: Deploy TimeLock ─────────────────────────────────────────────────
  console.log("\n[4/8] Deploying TimeLock...");
  const TimeLock = await ethers.getContractFactory("TimeLock");
  const timeLock = await TimeLock.deploy(deployed.gaiaToken, genesisCoordinator);
  await timeLock.waitForDeployment();
  deployed.timeLock = await timeLock.getAddress();
  console.log(`      TimeLock:           ${deployed.timeLock}`);
  console.log(`      GenesisCoordinator: ${genesisCoordinator}`);
  console.log(`      Expiry:             +18 months`);

  // ── Step 5: Deploy RewardDistributor ────────────────────────────────────────
  // Placeholder for validationPool and treasury (will update after step 6)
  // In production: use CREATE2 for deterministic addresses
  const TREASURY_PLACEHOLDER = deployer.address; // Replace with multisig
  console.log("\n[5/8] Deploying RewardDistributor...");
  const RewardDistributor = await ethers.getContractFactory("RewardDistributor");
  // Note: validationPool address is not yet known; use placeholder
  // Production deployment should use CREATE2 for deterministic ordering
  const rewardDistributor = await RewardDistributor.deploy(
    deployed.gaiaToken,
    deployer.address, // PLACEHOLDER — update after ValidationPool deploys
    TREASURY_PLACEHOLDER
  );
  await rewardDistributor.waitForDeployment();
  deployed.rewardDistributor = await rewardDistributor.getAddress();
  console.log(`      RewardDistributor:  ${deployed.rewardDistributor}`);

  // ── Step 6: Deploy ValidationPool ───────────────────────────────────────────
  console.log("\n[6/8] Deploying ValidationPool...");
  const ValidationPool = await ethers.getContractFactory("ValidationPool");
  const validationPool = await ValidationPool.deploy(
    deployer.address, // PLACEHOLDER for taskRegistry
    deployed.rewardDistributor,
    deployed.gaiaToken
  );
  await validationPool.waitForDeployment();
  deployed.validationPool = await validationPool.getAddress();
  console.log(`      ValidationPool:     ${deployed.validationPool}`);

  // ── Step 7: Deploy TaskRegistry ─────────────────────────────────────────────
  console.log("\n[7/8] Deploying TaskRegistry...");
  const TaskRegistry = await ethers.getContractFactory("TaskRegistry");
  const taskRegistry = await TaskRegistry.deploy(
    deployed.gaiaToken,
    deployed.frozenOracle,
    deployed.validationPool,
    deployed.rewardDistributor
  );
  await taskRegistry.waitForDeployment();
  deployed.taskRegistry = await taskRegistry.getAddress();
  console.log(`      TaskRegistry:       ${deployed.taskRegistry}`);

  // ── Step 8: Deploy GAIAProtocol (system registry) ───────────────────────────
  console.log("\n[8/8] Deploying GAIAProtocol...");
  const GAIAProtocol = await ethers.getContractFactory("GAIAProtocol");
  const gaiaProtocol = await GAIAProtocol.deploy(
    deployed.gaiaToken,
    deployed.convictionVoting,
    deployed.frozenOracle,
    deployed.taskRegistry,
    deployed.validationPool,
    deployed.rewardDistributor,
    deployed.timeLock
  );
  await gaiaProtocol.waitForDeployment();
  deployed.gaiaProtocol = await gaiaProtocol.getAddress();
  console.log(`      GAIAProtocol:       ${deployed.gaiaProtocol}`);

  // ── Genesis Setup ───────────────────────────────────────────────────────────
  console.log("\n── Genesis Setup ────────────────────────────────────────");

  // Initialize Oracle
  console.log("  Initializing FrozenOracle with model hash...");
  const initTx = await frozenOracle.initializeOracle(oracleModelHash, oracleModelCID);
  await initTx.wait();
  console.log(`  ✓ Oracle model hash: ${oracleModelHash}`);
  console.log(`  ✓ Oracle model CID:  ${oracleModelCID}`);
  console.log(`  ✓ Approved job types: ${await frozenOracle.approvedJobTypeCount()}`);

  // Transfer tokens to TimeLock for genesis allocation
  console.log("\n  Transferring token supply to TimeLock...");
  const totalSupply = await gaiaToken.totalSupply();
  const transferTx = await gaiaToken.transfer(deployed.timeLock, totalSupply);
  await transferTx.wait();
  console.log(`  ✓ ${ethers.formatEther(totalSupply)} GAIA → TimeLock`);

  // ── Deployment Summary ──────────────────────────────────────────────────────
  console.log("\n══════════════════════════════════════════════════════");
  console.log("  DEPLOYMENT COMPLETE");
  console.log("══════════════════════════════════════════════════════");
  console.log(JSON.stringify({
    network: hre.network.name,
    deployedAt: new Date().toISOString(),
    contracts: deployed,
    genesisCoordinator,
    oracleModelHash,
    oracleModelCID
  }, null, 2));

  console.log("\n── Next Steps (Genesis Ceremony) ────────────────────");
  console.log("  1. Replace PLACEHOLDER addresses with actual deployed addresses");
  console.log("  2. Execute TimeLock.createTeamAllocation() for each team member");
  console.log("  3. Use TimeLock.queueAction() + executeAction() for initial distribution");
  console.log("  4. Verify on-chain: all addresses match, oracle initialized");
  console.log("  5. Publish genesis record (block hash, all addresses, model CID)");
  console.log("  6. Genesis ceremony: 9 participants, 5 countries — contribute entropy");
  console.log("  7. After 18 months: call TimeLock.revokeGenesisAuthority()");
  console.log("     (or let it expire automatically — same security outcome)");
  console.log("══════════════════════════════════════════════════════\n");

  return deployed;
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error("Deployment failed:", error);
    process.exit(1);
  });
