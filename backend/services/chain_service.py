#!/usr/bin/env python3
"""services/chain_service.py — Flask ↔ PropertyToken bridge.

Talks to the local Hardhat network through web3.py using the exported
ABI and deployment metadata from the blockchain module (see
blockchain/INTEGRATION.md). Guarantees:

- Success is reported ONLY after the transaction receipt confirms
  (status == 1); reverted transactions surface as CHAIN_TX_FAILED.
- Duplicate registration is prevented twice: a store lookup by the
  valuation request id (the on-chain propertyRef) before sending, and
  the contract's own duplicate guard.
- Supply consistency is verified on-chain after registration:
  the contract's computed supply must equal the backend token
  service's floor(valuation_inr / denomination).
- When the chain is unreachable the API reports 503 CHAIN_UNAVAILABLE
  (the hosted-showcase behaviour from the architecture) — it never
  simulates a transaction.
"""
from __future__ import annotations

import json
import logging

from errors import ApiError
from models.chain_store import new_record
from models.history import DatabaseUnavailable


def _revert_error(exc: Exception) -> ApiError:
    """Map an on-chain revert to an honest API error instead of a 500:
    known duplicate conditions become 409s; anything else is a 502
    carrying the contract's revert reason."""
    message = str(exc)
    if "already registered" in message:
        return ApiError(409, "DUPLICATE_REGISTRATION",
                        "This property is already registered on-chain.")
    if "already minted" in message:
        return ApiError(409, "ALREADY_MINTED",
                        "Tokens for this property were already minted.")
    reason = message.split("execution reverted:")[-1].strip()[:300] \
        or "contract reverted"
    return ApiError(502, "CHAIN_TX_REVERTED",
                    f"The blockchain transaction reverted: {reason}")

logger = logging.getLogger("backend.chain_service")


class ChainService:
    def __init__(self, cfg, store, valuation_service, risk_service):
        self._rpc = cfg["CHAIN_RPC_URL"]
        self._deployment_file = cfg["CHAIN_DEPLOYMENT_FILE"]
        self._abi_file = cfg["CHAIN_ABI_FILE"]
        self._private_key = cfg["CHAIN_PRIVATE_KEY"]
        self._timeout = cfg["CHAIN_TX_TIMEOUT_S"]
        self._denomination = cfg["TOKEN_DENOMINATION_INR"]
        self._store = store
        self._valuation = valuation_service
        self._risk = risk_service
        self._w3 = None
        self._contract = None
        self._deployment = None
        self._connect_error: str | None = None

    # --- connection ------------------------------------------------------

    def _connect(self):
        """(Re)connect lazily; returns (w3, contract) or raises
        ApiError(503, CHAIN_UNAVAILABLE)."""
        if self._contract is not None:
            return self._w3, self._contract
        try:
            from web3 import Web3
            deployment = json.loads(self._deployment_file.read_text())
            abi = json.loads(self._abi_file.read_text())
            w3 = Web3(Web3.HTTPProvider(
                self._rpc, request_kwargs={"timeout": 5}))
            if not w3.is_connected():
                raise ConnectionError(f"no node at {self._rpc}")
            address = Web3.to_checksum_address(deployment["address"])
            if w3.eth.get_code(address) == b"":
                raise ConnectionError(
                    f"no contract code at {address} (not deployed)")
            self._w3 = w3
            self._deployment = deployment
            self._contract = w3.eth.contract(address=address, abi=abi)
            self._connect_error = None
            return self._w3, self._contract
        except ApiError:
            raise
        except Exception as exc:
            self._connect_error = str(exc)
            logger.warning("Chain unavailable: %s", exc)
            raise ApiError(503, "CHAIN_UNAVAILABLE",
                           "The local blockchain is unavailable. Start the "
                           "Hardhat node and deploy the contract, then retry.")

    def _admin_address(self, w3) -> str:
        if self._private_key:
            from eth_account import Account
            return Account.from_key(self._private_key).address
        return w3.eth.accounts[0]  # local node's unlocked account

    def _send(self, w3, contract_fn) -> dict:
        """Build, send and confirm a contract transaction. Returns the
        receipt as a dict. Raises ApiError on revert/timeout."""
        from web3.exceptions import TimeExhausted
        admin = self._admin_address(w3)
        tx = contract_fn.build_transaction({
            "from": admin,
            "nonce": w3.eth.get_transaction_count(admin),
            "chainId": w3.eth.chain_id,
        })
        if self._private_key:
            from eth_account import Account
            signed = Account.from_key(self._private_key).sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        else:
            tx_hash = w3.eth.send_transaction(tx)
        try:
            receipt = w3.eth.wait_for_transaction_receipt(
                tx_hash, timeout=self._timeout)
        except TimeExhausted:
            raise ApiError(504, "CHAIN_TX_TIMEOUT",
                           "The transaction was sent but not confirmed in "
                           f"time (hash {tx_hash.hex()}).")
        if receipt["status"] != 1:
            raise ApiError(502, "CHAIN_TX_FAILED",
                           "The blockchain transaction reverted "
                           f"(hash {tx_hash.hex()}).")
        tx_hex = tx_hash.hex()
        if not tx_hex.startswith("0x"):
            tx_hex = "0x" + tx_hex
        return {"hash": tx_hex, "block": int(receipt["blockNumber"]),
                "receipt": receipt}

    # --- status ------------------------------------------------------------

    def status(self) -> dict:
        base = {"rpc_url": self._rpc, "connected": False,
                "contract_address": None, "chain_id": None,
                "block_number": None, "admin_address": None,
                "connect_error": None}
        try:
            w3, _ = self._connect()
            base.update({
                "connected": True,
                "contract_address": self._deployment["address"],
                "chain_id": w3.eth.chain_id,
                "block_number": w3.eth.block_number,
                "admin_address": self._admin_address(w3),
                "network": self._deployment.get("network"),
            })
        except ApiError:
            base["connect_error"] = self._connect_error
        return base

    # --- register ------------------------------------------------------------

    @staticmethod
    def property_ref_for(features: dict) -> str:
        """Deterministic on-chain reference for a property: a hash of its
        canonical feature set. The same property always maps to the same
        reference, so re-registering it is detected as a duplicate (the
        per-request valuation id cannot serve this purpose — it changes
        on every call)."""
        import hashlib
        canonical = json.dumps(features, sort_keys=True, default=str)
        return "prop-" + hashlib.sha256(canonical.encode()).hexdigest()[:32]

    def register(self, request_id: str, features: dict) -> dict:
        property_ref = self.property_ref_for(features)
        # Duplicate prevention (application layer) before any chain call.
        try:
            existing = self._store.find_by_ref(property_ref)
        except DatabaseUnavailable:
            raise ApiError(503, "DATABASE_UNAVAILABLE",
                           "Tokenisation record store is unavailable.")
        if existing is not None:
            raise ApiError(409, "DUPLICATE_REGISTRATION",
                           "This valuation is already registered on-chain "
                           f"as property {existing['chain_property_id']} "
                           f"(tx {existing['register_tx']}).")

        w3, contract = self._connect()

        # Valuation + risk are computed by the existing services — the
        # same numbers the rest of the API reports.
        valuation = self._valuation.predict(request_id, features)
        price_lacs = valuation["predicted_price_lacs"]
        risk = self._risk.assess(features, price_lacs)
        valuation_inr = int(round(price_lacs * 100_000))
        expected_supply = valuation_inr // self._denomination

        # RiskService returns the engine's raw shape (overall_score /
        # category); the /api/risk route maps those to risk_score /
        # risk_category for API consumers.
        risk_score = float(risk["overall_score"])
        risk_category = str(risk["category"])
        from web3.exceptions import ContractLogicError
        try:
            sent = self._send(w3, contract.functions.registerProperty(
                property_ref, valuation_inr, int(round(risk_score)),
                risk_category))
        except ContractLogicError as exc:
            raise _revert_error(exc) from exc

        # Recover the new property id from the event log.
        property_id = None
        try:
            events = contract.events.PropertyRegistered().process_receipt(
                sent["receipt"])
            if events:
                property_id = int(events[0]["args"]["propertyId"])
        except Exception as exc:  # fall back to the sequential id
            logger.warning("Event parse failed (%s); using totalProperties",
                           exc)
        if property_id is None:
            property_id = int(contract.functions.totalProperties().call())

        # Verify the on-chain record against the backend's numbers.
        onchain = contract.functions.getProperty(property_id).call()
        supply_onchain = int(onchain[2])
        residual_onchain = int(onchain[3])
        if supply_onchain != expected_supply:
            raise ApiError(502, "CHAIN_STATE_MISMATCH",
                           "On-chain token supply does not match the "
                           "backend calculation; registration recorded but "
                           "flagged. Investigate before minting.")

        record = new_record(
            property_ref=property_ref, chain_property_id=property_id,
            valuation_inr=valuation_inr, risk_score=risk_score,
            risk_category=risk_category,
            token_supply=supply_onchain, residual_inr=residual_onchain,
            register_tx=sent["hash"], block_number=sent["block"],
            admin_address=self._admin_address(w3))
        record["valuation_request_id"] = request_id
        try:
            self._store.insert(record)
            record["record_saved"] = True
        except DatabaseUnavailable as exc:
            logger.error("Chain record save failed: %s", exc)
            record["record_saved"] = False
        record["valuation_lacs"] = price_lacs
        return record

    # --- mint ------------------------------------------------------------------

    def mint(self, chain_property_id: int) -> dict:
        try:
            record = self._store.find_by_chain_id(chain_property_id)
        except DatabaseUnavailable:
            raise ApiError(503, "DATABASE_UNAVAILABLE",
                           "Tokenisation record store is unavailable.")
        if record is None:
            raise ApiError(404, "PROPERTY_NOT_REGISTERED",
                           "No tokenisation record for this chain property "
                           "id. Register the property first.")
        if record["status"] == "minted":
            raise ApiError(409, "ALREADY_MINTED",
                           "Tokens for this property were already minted "
                           f"(tx {record['mint_tx']}).")

        w3, contract = self._connect()
        from web3.exceptions import ContractLogicError
        try:
            sent = self._send(
                w3, contract.functions.mintPropertyTokens(chain_property_id))
        except ContractLogicError as exc:
            raise _revert_error(exc) from exc

        # Verify the minted inventory on-chain before reporting success.
        inventory = int(contract.functions.balanceOf(
            self._deployment["address"], chain_property_id).call())
        if inventory != record["token_supply"]:
            raise ApiError(502, "CHAIN_STATE_MISMATCH",
                           "Minted inventory does not equal the recorded "
                           "token supply.")
        try:
            self._store.update(record["property_ref"],
                               {"mint_tx": sent["hash"], "status": "minted"})
            record["record_saved"] = True
        except DatabaseUnavailable:
            record["record_saved"] = False
        record["mint_tx"] = sent["hash"]
        record["mint_block"] = sent["block"]
        record["status"] = "minted"
        record["contract_inventory"] = inventory
        return record

    # --- reads -------------------------------------------------------------------

    def properties(self) -> dict:
        try:
            records = self._store.list()
        except DatabaseUnavailable:
            raise ApiError(503, "DATABASE_UNAVAILABLE",
                           "Tokenisation record store is unavailable.")
        connected = False
        try:
            w3, contract = self._connect()
            connected = True
            for rec in records:
                try:
                    rec["available_supply"] = int(
                        contract.functions.availableSupply(
                            rec["chain_property_id"]).call())
                except Exception:
                    rec["available_supply"] = None
        except ApiError:
            for rec in records:
                rec["available_supply"] = None
        return {"connected": connected, "properties": records}

    def property_detail(self, chain_property_id: int) -> dict:
        data = self.properties()
        for rec in data["properties"]:
            if rec["chain_property_id"] == int(chain_property_id):
                return rec
        raise ApiError(404, "PROPERTY_NOT_REGISTERED",
                       "No tokenisation record for this chain property id.")
