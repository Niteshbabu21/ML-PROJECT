// End-to-end demonstration on the local Hardhat network:
// register -> mint -> buy -> transfer, verifying every transaction and
// recording the real hashes in deployments/demo_verification.json.
//
// Inputs mirror the platform flow: an ML valuation of ₹98.21 lakh
// (₹9,821,000 -> 982 tokens, ₹1,000 residual) and a risk result
// (score 42, MEDIUM) as the risk engine would report for a listing.
// These are INPUTS to the demo; every on-chain output is read back from
// the chain itself.
//
// Usage (node running, contract deployed):
//   npx hardhat run scripts/demo-flow.js --network localhost
const fs = require("fs");
const path = require("path");
const hre = require("hardhat");

async function main() {
  const { ethers, network } = hre;
  const metaPath = path.join(
    __dirname, "..", "deployments", `${network.name}.json`
  );
  const meta = JSON.parse(fs.readFileSync(metaPath, "utf8"));
  const [admin, buyer, friend] = await ethers.getSigners();
  const token = await ethers.getContractAt("PropertyToken", meta.address);

  const record = { network: network.name, chainId: meta.chainId,
                   contract: meta.address, steps: [] };
  const step = (name, tx, extra = {}) => {
    record.steps.push({ name, txHash: tx.hash, ...extra });
    console.log(`${name}: ${tx.hash}`);
  };

  // 1. Register the property (valuation + risk recorded on-chain).
  const ref = "demo-valuation-9821000-inr";
  let tx = await token.registerProperty(ref, 9_821_000n, 42, "MEDIUM");
  await tx.wait();
  step("registerProperty", tx);
  const propertyId = (await token.totalProperties()); // ids are sequential
  const p = await token.getProperty(propertyId);
  console.log(
    `  property ${propertyId}: supply=${p.tokenSupply} residual=₹${p.residualInr} risk=${p.riskScore}/${p.riskCategory}`
  );

  // 2. Mint the supply to contract inventory.
  tx = await token.mintPropertyTokens(propertyId);
  await tx.wait();
  step("mintPropertyTokens", tx);

  // 3. Buyer purchases 100 tokens at the demo price.
  const price = await token.tokenPriceWei();
  tx = await token.connect(buyer).buyTokens(propertyId, 100, {
    value: 100n * price,
  });
  await tx.wait();
  step("buyTokens x100", tx, { buyer: buyer.address });

  // 4. Buyer transfers 40 tokens to a second wallet.
  tx = await token
    .connect(buyer)
    .safeTransferFrom(buyer.address, friend.address, propertyId, 40, "0x");
  await tx.wait();
  step("safeTransferFrom x40", tx, { from: buyer.address, to: friend.address });

  // 5. Read back final state from the chain.
  record.finalState = {
    propertyId: Number(propertyId),
    tokenSupply: Number(p.tokenSupply),
    residualInr: Number(p.residualInr),
    availableSupply: Number(await token.availableSupply(propertyId)),
    buyerBalance: Number(await token.balanceOf(buyer.address, propertyId)),
    friendBalance: Number(await token.balanceOf(friend.address, propertyId)),
    contractBalanceWei: (await ethers.provider.getBalance(meta.address)).toString(),
  };
  console.log("final state:", record.finalState);

  const out = path.join(__dirname, "..", "deployments", "demo_verification.json");
  fs.writeFileSync(out, JSON.stringify(record, null, 2));
  console.log("verification record:", out);
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
