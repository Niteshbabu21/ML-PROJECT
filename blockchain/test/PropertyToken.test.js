const { expect } = require("chai");
const { ethers } = require("hardhat");

// ₹98.21 lakh = ₹9,821,000 -> floor(/10000) = 982 tokens, ₹1,000 residual.
const VALUATION_INR = 9_821_000n;
const EXPECTED_SUPPLY = 982n;
const EXPECTED_RESIDUAL = 1_000n;
const PRICE_WEI = ethers.parseEther("0.001"); // demo test-ETH price

describe("PropertyToken", function () {
  let token, owner, registrar, buyer, stranger;
  const REF = "valuation-request-0001";

  beforeEach(async function () {
    [owner, registrar, buyer, stranger] = await ethers.getSigners();
    const Factory = await ethers.getContractFactory("PropertyToken");
    token = await Factory.deploy("https://example.invalid/meta/{id}.json", PRICE_WEI);
    await token.waitForDeployment();
  });

  async function registerAndMint() {
    await token.registerProperty(REF, VALUATION_INR, 42, "MEDIUM");
    await token.mintPropertyTokens(1);
  }

  describe("deployment", function () {
    it("deploys with the demo price and admin roles for the deployer", async function () {
      expect(await token.tokenPriceWei()).to.equal(PRICE_WEI);
      expect(await token.TOKEN_VALUE_INR()).to.equal(10_000n);
      const admin = await token.DEFAULT_ADMIN_ROLE();
      expect(await token.hasRole(admin, owner.address)).to.equal(true);
      expect(await token.totalProperties()).to.equal(0n);
    });

    it("computeSupply floors exactly like the Flask backend", async function () {
      expect(await token.computeSupply(VALUATION_INR)).to.equal(EXPECTED_SUPPLY);
      expect(await token.computeSupply(10_000n)).to.equal(1n);
      expect(await token.computeSupply(19_999n)).to.equal(1n);
    });
  });

  describe("property registration", function () {
    it("registers a property, computes floored supply and residual", async function () {
      await expect(token.registerProperty(REF, VALUATION_INR, 42, "MEDIUM"))
        .to.emit(token, "PropertyRegistered")
        .withArgs(1, REF, VALUATION_INR, EXPECTED_SUPPLY, EXPECTED_RESIDUAL, 42, "MEDIUM");
      const p = await token.getProperty(1);
      expect(p.propertyRef).to.equal(REF);
      expect(p.valuationInr).to.equal(VALUATION_INR);
      expect(p.tokenSupply).to.equal(EXPECTED_SUPPLY);
      expect(p.residualInr).to.equal(EXPECTED_RESIDUAL);
      expect(p.riskScore).to.equal(42);
      expect(p.riskCategory).to.equal("MEDIUM");
      expect(p.exists).to.equal(true);
      expect(await token.totalProperties()).to.equal(1n);
    });

    it("rejects duplicate registration of the same property reference", async function () {
      await token.registerProperty(REF, VALUATION_INR, 42, "MEDIUM");
      await expect(
        token.registerProperty(REF, VALUATION_INR, 10, "LOW")
      ).to.be.revertedWith("property already registered");
    });

    it("rejects invalid parameters", async function () {
      await expect(
        token.registerProperty("", VALUATION_INR, 42, "MEDIUM")
      ).to.be.revertedWith("empty propertyRef");
      await expect(
        token.registerProperty(REF, 9_999n, 42, "MEDIUM")
      ).to.be.revertedWith("valuation below one token");
      await expect(
        token.registerProperty(REF, VALUATION_INR, 101, "MEDIUM")
      ).to.be.revertedWith("riskScore > 100");
      await expect(
        token.registerProperty(REF, VALUATION_INR, 42, "SEVERE")
      ).to.be.revertedWith("invalid risk category");
    });

    it("rejects registration from an account without REGISTRAR_ROLE", async function () {
      await expect(
        token.connect(stranger).registerProperty(REF, VALUATION_INR, 42, "MEDIUM")
      ).to.be.reverted; // AccessControlUnauthorizedAccount
    });
  });

  describe("token minting", function () {
    it("mints the full supply to the contract inventory, once", async function () {
      await token.registerProperty(REF, VALUATION_INR, 42, "MEDIUM");
      await expect(token.mintPropertyTokens(1))
        .to.emit(token, "TokensMinted")
        .withArgs(1, EXPECTED_SUPPLY);
      const addr = await token.getAddress();
      expect(await token.balanceOf(addr, 1)).to.equal(EXPECTED_SUPPLY);
      await expect(token.mintPropertyTokens(1)).to.be.revertedWith("already minted");
    });

    it("rejects minting by an unauthorized account", async function () {
      await token.registerProperty(REF, VALUATION_INR, 42, "MEDIUM");
      await expect(token.connect(stranger).mintPropertyTokens(1)).to.be.reverted;
      await expect(token.connect(buyer).mintPropertyTokens(1)).to.be.reverted;
    });

    it("rejects minting an unknown property", async function () {
      await expect(token.mintPropertyTokens(99)).to.be.revertedWith("unknown property");
    });
  });

  describe("token purchases", function () {
    beforeEach(registerAndMint);

    it("sells tokens for exact payment and records the purchase", async function () {
      const cost = 100n * PRICE_WEI;
      await expect(token.connect(buyer).buyTokens(1, 100, { value: cost }))
        .to.emit(token, "TokensPurchased")
        .withArgs(buyer.address, 1, 100n, cost);
      expect(await token.balanceOf(buyer.address, 1)).to.equal(100n);
      expect(await token.availableSupply(1)).to.equal(EXPECTED_SUPPLY - 100n);
    });

    it("rejects incorrect payment", async function () {
      await expect(
        token.connect(buyer).buyTokens(1, 100, { value: 99n * PRICE_WEI })
      ).to.be.revertedWith("incorrect payment amount");
      await expect(
        token.connect(buyer).buyTokens(1, 100, { value: 101n * PRICE_WEI })
      ).to.be.revertedWith("incorrect payment amount");
    });

    it("rejects purchases exceeding the available supply", async function () {
      const tooMany = EXPECTED_SUPPLY + 1n;
      await expect(
        token.connect(buyer).buyTokens(1, tooMany, { value: tooMany * PRICE_WEI })
      ).to.be.revertedWith("insufficient supply available");
      // Buy out the full supply, then one more must fail.
      await token.connect(buyer).buyTokens(1, EXPECTED_SUPPLY, {
        value: EXPECTED_SUPPLY * PRICE_WEI,
      });
      await expect(
        token.connect(stranger).buyTokens(1, 1, { value: PRICE_WEI })
      ).to.be.revertedWith("insufficient supply available");
    });
  });

  describe("token transfers", function () {
    beforeEach(async function () {
      await registerAndMint();
      await token.connect(buyer).buyTokens(1, 100, { value: 100n * PRICE_WEI });
    });

    it("transfers tokens between wallets with events", async function () {
      await expect(
        token.connect(buyer).safeTransferFrom(buyer.address, stranger.address, 1, 40, "0x")
      )
        .to.emit(token, "TransferSingle")
        .withArgs(buyer.address, buyer.address, stranger.address, 1, 40n);
      expect(await token.balanceOf(buyer.address, 1)).to.equal(60n);
      expect(await token.balanceOf(stranger.address, 1)).to.equal(40n);
    });

    it("rejects transfers exceeding the balance", async function () {
      await expect(
        token.connect(buyer).safeTransferFrom(buyer.address, stranger.address, 1, 101, "0x")
      ).to.be.reverted; // ERC1155InsufficientBalance
    });
  });

  describe("ownership tracking", function () {
    it("reports per-account property holdings", async function () {
      await registerAndMint();
      await token.registerProperty("valuation-request-0002", 5_000_000n, 12, "LOW");
      await token.mintPropertyTokens(2);
      await token.connect(buyer).buyTokens(1, 100, { value: 100n * PRICE_WEI });
      await token.connect(buyer).buyTokens(2, 25, { value: 25n * PRICE_WEI });

      const [ids, balances] = await token.propertiesOf(buyer.address);
      expect(ids.map(Number)).to.deep.equal([1, 2]);
      expect(balances.map(Number)).to.deep.equal([100, 25]);

      const [emptyIds, emptyBalances] = await token.propertiesOf(stranger.address);
      expect(emptyIds.length).to.equal(0);
      expect(emptyBalances.length).to.equal(0);
    });
  });

  describe("administration", function () {
    it("lets the admin update the price and withdraw proceeds; blocks others", async function () {
      await registerAndMint();
      await token.connect(buyer).buyTokens(1, 10, { value: 10n * PRICE_WEI });

      await expect(token.connect(stranger).setTokenPriceWei(1n)).to.be.reverted;
      await token.setTokenPriceWei(ethers.parseEther("0.002"));
      expect(await token.tokenPriceWei()).to.equal(ethers.parseEther("0.002"));

      await expect(token.connect(stranger).withdrawProceeds()).to.be.reverted;
      await expect(token.withdrawProceeds()).to.emit(token, "ProceedsWithdrawn");
    });
  });
});
