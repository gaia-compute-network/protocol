const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("GAIAToken", function () {
  let gaiaToken;
  let owner, user1, user2;

  const TOTAL_SUPPLY = ethers.parseEther("21000000");
  const BURN_RATE_BPS = 500n; // 5%

  beforeEach(async function () {
    [owner, user1, user2] = await ethers.getSigners();

    const GAIAToken = await ethers.getContractFactory("GAIAToken");
    gaiaToken = await GAIAToken.deploy(owner.address);
  });

  describe("Deployment", function () {
    it("should have correct name and symbol", async function () {
      expect(await gaiaToken.name()).to.equal("GAIA");
      expect(await gaiaToken.symbol()).to.equal("GAIA");
    });

    it("should mint total supply to genesis receiver", async function () {
      const balance = await gaiaToken.balanceOf(owner.address);
      expect(balance).to.equal(TOTAL_SUPPLY);
    });

    it("should have correct total supply cap", async function () {
      expect(await gaiaToken.TOTAL_SUPPLY_CAP()).to.equal(TOTAL_SUPPLY);
    });

    it("should initialize totalBurned to 0", async function () {
      expect(await gaiaToken.totalBurned()).to.equal(0n);
    });
  });

  describe("Burn Functionality", function () {
    it("should burn tokens and increase totalBurned", async function () {
      const burnAmount = ethers.parseEther("1000");

      await expect(
        gaiaToken.burnWithReason(burnAmount, "test_burn")
      ).to.emit(gaiaToken, "TokensBurned")
        .withArgs(owner.address, burnAmount, "test_burn");

      expect(await gaiaToken.totalBurned()).to.equal(burnAmount);
      expect(await gaiaToken.balanceOf(owner.address)).to.equal(
        TOTAL_SUPPLY - burnAmount
      );
    });

    it("should track multiple burns correctly", async function () {
      const burn1 = ethers.parseEther("500");
      const burn2 = ethers.parseEther("1000");

      await gaiaToken.burnWithReason(burn1, "burn1");
      await gaiaToken.burnWithReason(burn2, "burn2");

      expect(await gaiaToken.totalBurned()).to.equal(burn1 + burn2);
    });

    it("should allow user to burn their own tokens", async function () {
      const amount = ethers.parseEther("100");
      await gaiaToken.transfer(user1.address, amount);

      await gaiaToken.connect(user1).burnWithReason(amount, "user_burn");

      expect(await gaiaToken.balanceOf(user1.address)).to.equal(0n);
      expect(await gaiaToken.totalBurned()).to.equal(amount);
    });

    it("should burn from account with burnFromWithReason", async function () {
      const amount = ethers.parseEther("500");
      await gaiaToken.transfer(user1.address, amount);
      await gaiaToken.connect(user1).approve(user2.address, amount);

      await gaiaToken.connect(user2).burnFromWithReason(
        user1.address,
        amount,
        "slash_penalty"
      );

      expect(await gaiaToken.balanceOf(user1.address)).to.equal(0n);
      expect(await gaiaToken.totalBurned()).to.equal(amount);
    });

    it("should revert burnFromWithReason with insufficient allowance", async function () {
      const amount = ethers.parseEther("100");
      await gaiaToken.transfer(user1.address, amount);
      await gaiaToken.connect(user1).approve(user2.address, ethers.parseEther("50"));

      await expect(
        gaiaToken.connect(user2).burnFromWithReason(
          user1.address,
          amount,
          "penalty"
        )
      ).to.be.reverted;
    });
  });

  describe("Supply and Burn Tracking", function () {
    it("should have BURN_RATE_BPS constant equal to 500", async function () {
      expect(await gaiaToken.BURN_RATE_BPS()).to.equal(BURN_RATE_BPS);
    });

    it("should correctly calculate circulating supply", async function () {
      const burnAmount = ethers.parseEther("1000000");
      await gaiaToken.burnWithReason(burnAmount, "test");

      const circulatingSupply = await gaiaToken.circulatingSupply();
      expect(circulatingSupply).to.equal(TOTAL_SUPPLY - burnAmount);
    });

    it("should calculate burned basis points correctly", async function () {
      const burnAmount = ethers.parseEther("2100000"); // 10% of supply
      await gaiaToken.burnWithReason(burnAmount, "test");

      const burnedBps = await gaiaToken.burnedBps();
      expect(burnedBps).to.equal(1000n); // 10% = 1000 bps
    });

    it("should handle zero totalBurned in burnedBps", async function () {
      const burnedBps = await gaiaToken.burnedBps();
      expect(burnedBps).to.equal(0n);
    });
  });

  describe("Transfer and Approval", function () {
    it("should transfer tokens between accounts", async function () {
      const amount = ethers.parseEther("100");
      await gaiaToken.transfer(user1.address, amount);

      expect(await gaiaToken.balanceOf(user1.address)).to.equal(amount);
    });

    it("should approve and transferFrom", async function () {
      const amount = ethers.parseEther("100");
      await gaiaToken.transfer(user1.address, amount);
      await gaiaToken.connect(user1).approve(user2.address, amount);

      await gaiaToken.connect(user2).transferFrom(
        user1.address,
        user2.address,
        amount
      );

      expect(await gaiaToken.balanceOf(user2.address)).to.equal(amount);
    });

    it("should revert transfer if balance insufficient", async function () {
      const amount = ethers.parseEther("100");
      await expect(
        gaiaToken.connect(user1).transfer(user2.address, amount)
      ).to.be.reverted;
    });
  });

  describe("Permit (EIP-2612)", function () {
    it("should allow permit signature", async function () {
      const amount = ethers.parseEther("100");
      const nonce = await gaiaToken.nonces(owner.address);
      const deadline = (await ethers.provider.getBlock("latest")).timestamp + 86400;

      const domain = {
        name: await gaiaToken.name(),
        version: "1",
        chainId: (await ethers.provider.getNetwork()).chainId,
        verifyingContract: await gaiaToken.getAddress(),
      };

      const types = {
        Permit: [
          { name: "owner", type: "address" },
          { name: "spender", type: "address" },
          { name: "value", type: "uint256" },
          { name: "nonce", type: "uint256" },
          { name: "deadline", type: "uint256" },
        ],
      };

      const value = {
        owner: owner.address,
        spender: user1.address,
        value: amount,
        nonce: nonce,
        deadline: deadline,
      };

      const signature = await owner.signTypedData(domain, types, value);
      const { v, r, s } = ethers.Signature.from(signature);

      await gaiaToken.permit(
        owner.address,
        user1.address,
        amount,
        deadline,
        v,
        r,
        s
      );

      expect(await gaiaToken.allowance(owner.address, user1.address)).to.equal(
        amount
      );
    });
  });

  describe("Edge Cases", function () {
    it("should handle burning zero tokens", async function () {
      await gaiaToken.burnWithReason(0n, "zero_burn");
      expect(await gaiaToken.totalBurned()).to.equal(0n);
    });

    it("should prevent transfer to zero address", async function () {
      const amount = ethers.parseEther("100");
      await expect(
        gaiaToken.transfer(ethers.ZeroAddress, amount)
      ).to.be.reverted;
    });

    it("should prevent burn exceeding balance", async function () {
      const amount = ethers.parseEther("100");
      await gaiaToken.transfer(user1.address, amount);

      await expect(
        gaiaToken.connect(user1).burnWithReason(amount + 1n, "overspend")
      ).to.be.reverted;
    });
  });
});
