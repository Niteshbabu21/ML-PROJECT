"""chain_store.py — persistence for blockchain tokenisation records.

One record per registered property, keyed by the valuation request id
(the same reference stored on-chain as `propertyRef`), so database and
blockchain identities stay consistent:

    valuation request_id  ==  record.property_ref  ==  on-chain propertyRef
    record.chain_property_id == on-chain token id

MongoDB (collection `tokenisations`) with the same degradation pattern
as the valuation history: when MongoDB is unreachable, writes raise
DatabaseUnavailable and the API reports it cleanly.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from models.history import DatabaseUnavailable

logger = logging.getLogger("backend.chain_store")


def new_record(*, property_ref: str, chain_property_id: int,
               valuation_inr: int, risk_score: float, risk_category: str,
               token_supply: int, residual_inr: int, register_tx: str,
               block_number: int, admin_address: str) -> dict:
    return {
        "property_ref": property_ref,
        "chain_property_id": int(chain_property_id),
        "valuation_inr": int(valuation_inr),
        "risk_score": risk_score,
        "risk_category": risk_category,
        "token_supply": int(token_supply),
        "residual_inr": int(residual_inr),
        "register_tx": register_tx,
        "register_block": int(block_number),
        "mint_tx": None,
        "status": "registered",
        "admin_address": admin_address,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


class MongoChainStore:
    def __init__(self, uri: str, db_name: str, collection: str,
                 timeout_ms: int = 1500):
        from pymongo import MongoClient
        self._client = MongoClient(uri, serverSelectionTimeoutMS=timeout_ms)
        self._collection = self._client[db_name][collection]

    def _guard(self, fn):
        try:
            return fn()
        except Exception as exc:
            raise DatabaseUnavailable(str(exc)) from exc

    def find_by_ref(self, property_ref: str):
        doc = self._guard(
            lambda: self._collection.find_one({"property_ref": property_ref}))
        return _clean(doc)

    def find_by_chain_id(self, chain_property_id: int):
        doc = self._guard(lambda: self._collection.find_one(
            {"chain_property_id": int(chain_property_id)}))
        return _clean(doc)

    def insert(self, record: dict):
        self._guard(lambda: self._collection.insert_one(dict(record)))
        return record

    def update(self, property_ref: str, fields: dict):
        fields = {**fields,
                  "updated_at": datetime.now(timezone.utc).isoformat()}
        self._guard(lambda: self._collection.update_one(
            {"property_ref": property_ref}, {"$set": fields}))

    def list(self):
        docs = self._guard(lambda: list(
            self._collection.find().sort("created_at", -1)))
        return [_clean(d) for d in docs]


class InMemoryChainStore:
    """Process-local store with the identical interface (dev/testing)."""

    def __init__(self):
        self._records: dict[str, dict] = {}

    def find_by_ref(self, property_ref: str):
        rec = self._records.get(property_ref)
        return dict(rec) if rec else None

    def find_by_chain_id(self, chain_property_id: int):
        for rec in self._records.values():
            if rec["chain_property_id"] == int(chain_property_id):
                return dict(rec)
        return None

    def insert(self, record: dict):
        self._records[record["property_ref"]] = dict(record)
        return record

    def update(self, property_ref: str, fields: dict):
        if property_ref in self._records:
            self._records[property_ref].update(fields)
            self._records[property_ref]["updated_at"] = datetime.now(
                timezone.utc).isoformat()

    def list(self):
        return [dict(r) for r in sorted(
            self._records.values(),
            key=lambda r: r["created_at"], reverse=True)]


def _clean(doc):
    if doc is None:
        return None
    doc = dict(doc)
    doc.pop("_id", None)
    return doc
