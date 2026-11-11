// Deploy PropertyToken to the selected network (local Hardhat chain)
// and write deployment metadata + the ABI the Flask bridge consumes.
//
// Usage: npx hardhat run scripts/deploy.js --network localhost
const fs = require("fs");
const path = require("path");
const hre = require("hardhat");

async function main() {
  const { ethers, network } = hre;
  const [deployer] = await ethers.getSigners();
  const tokenPriceWei = ethers.parseEther("0.001"); // demo test-ETH price
  const metadataUri = "https://example.invalid/property-token/{id}.json";

  const Factory = await ethers.getContractFactory("PropertyToken");
  const token = await Factory.deploy(metadataUri, tokenPriceWei);
  await token.waitForDeployment();
  const address = await token.getAddress();
  const deployTx = token.deploymentTransaction();

  const chainId = Number((await ethers.provider.getNetwork()).chainId);
  const meta = {
    contract: "PropertyToken",
    address,
    deployer: deployer.address,
    network: network.name,
    chainId,
    deploymentTxHash: deployTx ? deployTx.hash : null,
    tokenPriceWei: tokenPriceWei.toString(),
    tokenValueInr: 10000,
    metadataUri,
    deployedAt: new Date().toISOString(),
    note: "Local Hardhat network deployment for an academic prototype. These tokens do not legally represent ownership of physical property.",
  };

  const dir = path.join(__dirname, "..", "deployments");
  fs.mkdirSync(dir, { recursive: true });
  const file = path.join(dir, `${network.name}.json`);
  fs.writeFileSync(file, JSON.stringify(meta, null, 2));

  const artifact = await hre.artifacts.readArtifact("PropertyToken");
  const abiDir = path.join(__dirname, "..", "abi");
  fs.mkdirSync(abiDir, { recursive: true });
  fs.writeFileSync(
    path.join(abiDir, "PropertyToken.json"),
    JSON.stringify(artifact.abi, null, 2)
  );

  console.log("PropertyToken deployed");
  console.log("  network:      ", network.name, `(chain ${chainId})`);
  console.log("  address:      ", address);
  console.log("  deployer:     ", deployer.address);
  console.log("  deploy tx:    ", meta.deploymentTxHash);
  console.log("  metadata:     ", file);
  console.log("  abi:          ", path.join(abiDir, "PropertyToken.json"));
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
