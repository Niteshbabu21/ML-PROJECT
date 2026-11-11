// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {ERC1155} from "@openzeppelin/contracts/token/ERC1155/ERC1155.sol";
import {ERC1155Holder} from "@openzeppelin/contracts/token/ERC1155/utils/ERC1155Holder.sol";
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * @title PropertyToken
 * @notice Fractional token representation of ML-valued properties for an
 *         ACADEMIC PROTOTYPE on a local Hardhat network.
 *
 *         These tokens do NOT legally represent ownership of, title to, or
 *         any claim on physical property. They are a software
 *         representation of a valuation figure produced by the project's
 *         ML model, used to demonstrate risk-aware tokenisation mechanics.
 *
 * @dev Design:
 *      - ERC-1155: one token id per registered property; each id's units
 *        are the fractional tokens of that property.
 *      - Token economics mirror the Flask backend exactly:
 *            tokenSupply = valuationINR / TOKEN_VALUE_INR   (floor)
 *        with TOKEN_VALUE_INR = 10_000 (each token represents ₹10,000 of
 *        the ML-predicted valuation). Integer division in Solidity floors
 *        automatically; the residual (valuationINR % 10_000) is stored on
 *        chain as `residualInr` and remains untokenised, so issued supply
 *        can never exceed the valuation. No floating point is used:
 *        valuations arrive as whole Indian rupees (uint256).
 *      - Purchases use a fixed DEMO price in test ETH
 *        (tokenPriceWei, default 0.001 ether per token). This is a local
 *        test-network constant, NOT a market price and NOT an FX rate.
 *      - Roles: DEFAULT_ADMIN_ROLE (deployer) administers; REGISTRAR_ROLE
 *        registers properties; MINTER_ROLE mints a property's supply
 *        (minting goes to the contract itself, which then sells from its
 *        own inventory — buyers never mint).
 */
contract PropertyToken is ERC1155, ERC1155Holder, AccessControl, ReentrancyGuard {
    bytes32 public constant REGISTRAR_ROLE = keccak256("REGISTRAR_ROLE");
    bytes32 public constant MINTER_ROLE = keccak256("MINTER_ROLE");

    /// @notice Value each token represents, in whole INR (₹10,000).
    uint256 public constant TOKEN_VALUE_INR = 10_000;

    struct Property {
        string propertyRef; // off-chain reference (valuation request id)
        uint256 valuationInr; // ML-predicted valuation, whole INR
        uint256 tokenSupply; // floor(valuationInr / TOKEN_VALUE_INR)
        uint256 residualInr; // valuationInr % TOKEN_VALUE_INR (untokenised)
        uint256 sold; // tokens sold from contract inventory
        uint8 riskScore; // 0..100, from the backend risk engine
        string riskCategory; // "LOW" | "MEDIUM" | "HIGH"
        bool minted;
        bool exists;
    }

    uint256 private _nextPropertyId = 1;
    mapping(uint256 => Property) private _properties;
    mapping(bytes32 => bool) private _registeredRefs; // duplicate guard
    uint256[] private _propertyIds;

    /// @notice Demo purchase price per token, in wei (test ETH only).
    uint256 public tokenPriceWei;

    event PropertyRegistered(
        uint256 indexed propertyId,
        string propertyRef,
        uint256 valuationInr,
        uint256 tokenSupply,
        uint256 residualInr,
        uint8 riskScore,
        string riskCategory
    );
    event TokensMinted(uint256 indexed propertyId, uint256 supply);
    event TokensPurchased(
        address indexed buyer,
        uint256 indexed propertyId,
        uint256 amount,
        uint256 paidWei
    );
    event TokenPriceUpdated(uint256 newPriceWei);
    event ProceedsWithdrawn(address indexed to, uint256 amountWei);

    constructor(
        string memory metadataUri,
        uint256 initialTokenPriceWei
    ) ERC1155(metadataUri) {
        require(initialTokenPriceWei > 0, "price must be > 0");
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(REGISTRAR_ROLE, msg.sender);
        _grantRole(MINTER_ROLE, msg.sender);
        tokenPriceWei = initialTokenPriceWei;
    }

    // --- Property registration -------------------------------------------

    /**
     * @notice Register a valued property. The token supply is computed
     *         on-chain from the valuation with floor division.
     * @param propertyRef  unique off-chain reference (e.g. the valuation
     *                     request id from the Flask backend)
     * @param valuationInr ML-predicted valuation in whole INR (> 0)
     * @param riskScore    risk score 0..100 from the backend risk engine
     * @param riskCategory "LOW", "MEDIUM" or "HIGH"
     * @return propertyId  the newly assigned token id
     */
    function registerProperty(
        string calldata propertyRef,
        uint256 valuationInr,
        uint8 riskScore,
        string calldata riskCategory
    ) external onlyRole(REGISTRAR_ROLE) returns (uint256 propertyId) {
        require(bytes(propertyRef).length > 0, "empty propertyRef");
        require(valuationInr >= TOKEN_VALUE_INR, "valuation below one token");
        require(riskScore <= 100, "riskScore > 100");
        require(_isValidCategory(riskCategory), "invalid risk category");
        bytes32 refHash = keccak256(bytes(propertyRef));
        require(!_registeredRefs[refHash], "property already registered");

        uint256 supply = computeSupply(valuationInr);
        uint256 residual = valuationInr % TOKEN_VALUE_INR;

        propertyId = _nextPropertyId++;
        _properties[propertyId] = Property({
            propertyRef: propertyRef,
            valuationInr: valuationInr,
            tokenSupply: supply,
            residualInr: residual,
            sold: 0,
            riskScore: riskScore,
            riskCategory: riskCategory,
            minted: false,
            exists: true
        });
        _registeredRefs[refHash] = true;
        _propertyIds.push(propertyId);

        emit PropertyRegistered(
            propertyId,
            propertyRef,
            valuationInr,
            supply,
            residual,
            riskScore,
            riskCategory
        );
    }

    // --- Token creation ----------------------------------------------------

    /**
     * @notice Mint the full computed supply of a registered property to
     *         the contract's own inventory (from which purchases are
     *         fulfilled). Callable once per property, MINTER_ROLE only —
     *         buyers and the public can never mint.
     */
    function mintPropertyTokens(
        uint256 propertyId
    ) external onlyRole(MINTER_ROLE) {
        Property storage p = _properties[propertyId];
        require(p.exists, "unknown property");
        require(!p.minted, "already minted");
        p.minted = true;
        _mint(address(this), propertyId, p.tokenSupply, "");
        emit TokensMinted(propertyId, p.tokenSupply);
    }

    // --- Token purchase ----------------------------------------------------

    /**
     * @notice Buy `amount` tokens of a property at the demo test-ETH
     *         price. Payment must equal amount * tokenPriceWei exactly;
     *         the contract's remaining inventory must cover the amount.
     */
    function buyTokens(
        uint256 propertyId,
        uint256 amount
    ) external payable nonReentrant {
        Property storage p = _properties[propertyId];
        require(p.exists, "unknown property");
        require(p.minted, "tokens not minted yet");
        require(amount > 0, "amount must be > 0");
        uint256 cost = amount * tokenPriceWei;
        require(msg.value == cost, "incorrect payment amount");
        uint256 available = p.tokenSupply - p.sold;
        require(amount <= available, "insufficient supply available");

        p.sold += amount;
        _safeTransferFrom(address(this), msg.sender, propertyId, amount, "");
        emit TokensPurchased(msg.sender, propertyId, amount, msg.value);
    }

    // --- Ownership / views ---------------------------------------------------

    /// @notice The project tokenomics formula, on-chain:
    ///         floor(valuationInr / 10_000). Pure integer arithmetic.
    function computeSupply(
        uint256 valuationInr
    ) public pure returns (uint256) {
        return valuationInr / TOKEN_VALUE_INR;
    }

    function getProperty(
        uint256 propertyId
    ) external view returns (Property memory) {
        require(_properties[propertyId].exists, "unknown property");
        return _properties[propertyId];
    }

    function totalProperties() external view returns (uint256) {
        return _propertyIds.length;
    }

    function availableSupply(
        uint256 propertyId
    ) external view returns (uint256) {
        Property storage p = _properties[propertyId];
        require(p.exists, "unknown property");
        return p.tokenSupply - p.sold;
    }

    /// @notice All property ids an account holds a positive balance of,
    ///         with the balances — the ownership overview for the UI.
    function propertiesOf(
        address account
    )
        external
        view
        returns (uint256[] memory ids, uint256[] memory balances)
    {
        uint256 count = 0;
        for (uint256 i = 0; i < _propertyIds.length; i++) {
            if (balanceOf(account, _propertyIds[i]) > 0) count++;
        }
        ids = new uint256[](count);
        balances = new uint256[](count);
        uint256 j = 0;
        for (uint256 i = 0; i < _propertyIds.length; i++) {
            uint256 bal = balanceOf(account, _propertyIds[i]);
            if (bal > 0) {
                ids[j] = _propertyIds[i];
                balances[j] = bal;
                j++;
            }
        }
    }

    // --- Administration ------------------------------------------------------

    function setTokenPriceWei(
        uint256 newPriceWei
    ) external onlyRole(DEFAULT_ADMIN_ROLE) {
        require(newPriceWei > 0, "price must be > 0");
        tokenPriceWei = newPriceWei;
        emit TokenPriceUpdated(newPriceWei);
    }

    /// @notice Withdraw accumulated test-ETH proceeds (admin only).
    function withdrawProceeds() external onlyRole(DEFAULT_ADMIN_ROLE) nonReentrant {
        uint256 amount = address(this).balance;
        require(amount > 0, "no proceeds");
        (bool ok, ) = payable(msg.sender).call{value: amount}("");
        require(ok, "withdraw failed");
        emit ProceedsWithdrawn(msg.sender, amount);
    }

    // --- Internals -------------------------------------------------------------

    function _isValidCategory(
        string calldata category
    ) internal pure returns (bool) {
        bytes32 h = keccak256(bytes(category));
        return
            h == keccak256("LOW") ||
            h == keccak256("MEDIUM") ||
            h == keccak256("HIGH");
    }

    function supportsInterface(
        bytes4 interfaceId
    )
        public
        view
        override(ERC1155, ERC1155Holder, AccessControl)
        returns (bool)
    {
        return super.supportsInterface(interfaceId);
    }
}
