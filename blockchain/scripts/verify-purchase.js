// Verify step 8 (purchase + transfer) against a property that was
// registered and minted THROUGH THE FLASK API (not by these scripts):
// a buyer wallet purchases tokens of chain property 1 and transfers
// some to a third wallet; all balances are read back from the chain
// and written to deployments/integration_verification.json.
//
// Usage (node running, Flask-registered property 1 minted):
//   npx hardhat run scripts/verify-purchase.js --network localhost
const fs = require("fs");
const path = require("path");
const hre = require("hardhat");

async function main() {
  const { ethers, network } = hre;
  const meta = JSON.parse(
    fs.readFileSync(path.join(__dirname, "..", "deployments", "localhost.json"), "utf8")
  );
  const [, buyer, friend] = await ethers.getSigners();
  const token = await ethers.getContractAt("PropertyToken", meta.address);
  const propertyId = 1n;

  const price = await token.tokenPriceWei();
  const record = { propertyId: Number(propertyId), steps: [] };

  let tx = await token.connect(buyer).buyTokens(propertyId, 25, {
    value: 25n * price,
  });
  await tx.wait();
  record.steps.push({ name: "buyTokens x25 (wallet flow)", txHash: tx.hash });
  console.log("buy:", tx.hash);

  tx = await token
    .connect(buyer)
    .safeTransferFrom(buyer.address, friend.address, propertyId, 10, "0x");
  await tx.wait();
  record.steps.push({ name: "safeTransferFrom x10", txHash: tx.hash });
  console.log("transfer:", tx.hash);

  record.finalState = {
    buyerBalance: Number(await token.balanceOf(buyer.address, propertyId)),
    friendBalance: Number(await token.balanceOf(friend.address, propertyId)),
    availableSupply: Number(await token.availableSupply(propertyId)),
  };
  console.log("final state:", record.finalState);

  fs.writeFileSync(
    path.join(__dirname, "..", "deployments", "integration_verification.json"),
    JSON.stringify(record, null, 2)
  );
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
