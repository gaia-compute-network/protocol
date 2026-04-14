/**
 * GAIA Protocol — Hardhat Deployment Script (Fixed Circular Dependencies)
 *
 * Deploys all 8 contracts in the correct order, using setAddresses() pattern
 * to break circular dependencies between ValidationPool and RewardDistributor.
 *
 * Deployment order:
 *   1. GAIAToken
 *   2. ConvictionVoting
 *   3. FrozenOracle
 *   4. TimeLock
 *   5. RewardDistributor (without validationPool)
 *   6. TaskRegistry (needs validationPool)
 *   7. ValidationPool (without taskRegistry/rewardDistributor)
 *   8. setAddresses() calls to wire up the circular dependencies
 *   9. GAIAProtocol
 *  10. Initialize oracle & transfer tokens to TimeLock
 *
 * Run with:
 *   npx hardhat run scripts/deploy.js --network <arbitrum-goerli|mainnet>
 *
 * Environment variables required:
 *   GENESIS_COORDINATOR_ADDRESS  — multi-sig of genesis ceremony participants
 *   PRIVATE_KEY                  — deployer private key
 *   RPC_URL                      — node RPC endpoint
 *   ORACLE_MODEL_HASH            — bytes32 SHA-256 of oracle model weights
 *   ORACLE_MODEL_CID             — IPFS CID of oracle model
 */

const hre = require("hardhat");
const { ethers } = require("hardhat");

async function main() {
  const [deployer] = await ethers.getSigners();
  console.log("══════════════════════════════════════════════════════");
  console.log("  GAIA Protocol — Genesis Deployment (Circular Deps Fixed)");
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

  // Step 1: Deploy GAIAToken
  console.log("\n[1/10] Deploying GAIAToken...");
  const GAIAToken = await ethers.getContractFactory("GAIAToken");
  const gaiaToken = await GAIAToken.deploy(deployer.address);
  await gaiaToken.waitForDeployment();
  deployed.gaiaToken = await gaiaToken.getAddress();
  console.log(`      OK GAIAToken: ${deployed.gaiaToken}`);

  // Step 2: Deploy ConvictionVoting
  console.log("\n[2/10] Deploying ConvictionVoting...");
  const ConvictionVoting = await ethers.getContractFactory("ConvictionVoting");
  const convictionVoting = await ConvictionVoting.deploy(deployed.gaiaToken);
  await convictionVoting.waitForDeployment();
  deployed.convictionVoting = await convictionVoting.getAddress();
  console.log(`      OK ConvictionVoting: ${deployed.convictionVoting}`);

  // Step 3: Deploy FrozenOracle
  console.log("\n[3/10] Deploying FrozenOracle...");
  const FrozenOracle = await ethers.getContractFactory("FrozenOracle");
  const frozenOracle = await FrozenOracle.deploy(deployed.convictionVoting);
  await frozenOracle.waitForDeployment();
  deployed.frozenOracle = await frozenOracle.getAddress();
  console.log(`      OK FrozenOracle: ${deployed.frozenOracle}`);

  // Step 4: Deploy TimeLock
  console.log("\n[4/10] Deploying TimeLock...");
  const TimeLock = await ethers.getContractFactory("TimeLock");
  const timeLock = await TimeLock.deploy(deployed.gaiaToken, genesisCoordinator);
  await timeLock.waitForDeployment();
  deployed.timeLock = await timeLock.getAddress();
  console.log(`      OK TimeLock: ${deployed.timeLock}`);

  // Step 5: Deploy RewardDistributor (without validationPool)
  console.log("\n[5/10] Deploying RewardDistributor (without validationPool)...");
  const RewardDistributor = await ethers.getContractFactory("RewardDistributor");
  const rewardDistributor = await RewardDistributor.deploy(
    deployed.gaiaToken,
    deployer.address  // TREASURY
  );
  await rewardDistributor.waitForDeployment();
  deployed.rewardDistributor = await rewardDistributor.getAddress();
  console.log(`      OK RewardDistributor: ${deployed.rewardDistributor}`);
  console.log(`      INFO validationPool will be set via setValidationPool() later`);

  // Step 6: Deploy TaskRegistry
  console.log("\n[6/10] Deploying TaskRegistry...");
  const TaskRegistry = await ethers.getContractFactory("TaskRegistry");
  const taskRegistry = await TaskRegistry.deploy(
    deployed.gaiaToken,
    deployed.frozenOracle,
    deployer.address,  // PLACEHOLDER for validationPool
    deployed.rewardDistributor
  );
  await taskRegistry.waitForDeployment();
  deployed.taskRegistry = await taskRegistry.getAddress();
  console.log(`      OK TaskRegistry: ${deployed.taskRegistry}`);
  console.log(`      INFO validationPool placeholder will be updated via setAddresses()`);

  // Step 7: Deploy ValidationPool (without circular deps)
  console.log("\n[7/10] Deploying ValidationPool (without circular deps)...");
  const ValidationPool = await ethers.getContractFactory("ValidationPool");
  const validationPool = await ValidationPool.deploy(deployed.gaiaToken);
  await validationPool.waitForDeployment();
  deployed.validationPool = await validationPool.getAddress();
  console.log(`      OK ValidationPool: ${deployed.validationPool}`);
  console.log(`      INFO taskRegistry & rewardDistributor will be set via setAddresses()`);

  // Step 8: Wire up circular dependencies
  console.log("\n[8/10] Wiring up circular dependencies...");

  // 8a. ValidationPool.setAddresses(taskRegistry, rewardDistributor)
  console.log("      Setting ValidationPool addresses...");
  const vp_setTx = await validationPool.setAddresses(
    deployed.taskRegistry,
    deployed.rewardDistributor
  );
  await vp_setTx.wait();
  console.log(`      OK ValidationPool.setAddresses() called`);

  // 8b. RewardDistributor.setValidationPool(validationPool)
  console.log("      Setting RewardDistributor validationPool...");
  const rd_setTx = await rewardDistributor.setValidationPool(deployed.validationPool);
  await rd_setTx.wait();
  console.log(`      OK RewardDistributor.setValidationPool() called`);

  // 8c. Update TaskRegistry validationPool if setter exists
  if (taskRegistry.setValidationPool && typeof taskRegistry.setValidationPool === 'function') {
    console.log("      Setting TaskRegistry validationPool...");
    const tr_setTx = await taskRegistry.setValidationPool(deployed.validationPool);
    await tr_setTx.wait();
    console.log(`      OK TaskRegistry.setValidationPool() called`);
  }

  // Step 9: Deploy GAIAProtocol
  console.log("\n[9/10] Deploying GAIAProtocol...");
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
  console.log(`      OK GAIAProtocol: ${deployed.gaiaProtocol}`);

  // Step 10: Genesis Setup
  console.log("\n[10/10] Genesis Setup...");

  // Initialize Oracle
  console.log("      Initializing FrozenOracle with model hash...");
  const initTx = await frozenOracle.initializeOracle(oracleModelHash, oracleModelCID);
  await initTx.wait();
  console.log(`      OK Oracle initialized`);

  // Transfer tokens to TimeLock
  console.log("      Transferring token supply to TimeLock...");
  const totalSupply = await gaiaToken.totalSupply();
  const transferTx = await gaiaToken.transfer(deployed.timeLock, totalSupply);
  await transferTx.wait();
  console.log(`      OK ${ethers.formatEther(totalSupply)} GAIA transferred to TimeLock`);

  // Deployment Summary
  console.log("\n══════════════════════════════════════════════════════");
  console.log("  DEPLOYMENT COMPLETE — Circular Dependencies Fixed");
  console.log("══════════════════════════════════════════════════════");
  console.log(JSON.stringify({
    network: hre.network.name,
    deployedAt: new Date().toISOString(),
    contracts: deployed,
    genesisCoordinator
  }, null, 2));

  console.log("\n══════════════════════════════════════════════════════\n");

  return deployed;
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error("Deployment failed:", error);
    process.exit(1);
  });
