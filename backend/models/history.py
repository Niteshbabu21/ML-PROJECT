#!/usr/bin/env python3
"""models/history.py — valuation history persistence.

A history record captures one valuation event: the request id, the
timestamp, the submitted property features, the predicted price, the
currency and the model identifier.

Two repository implementations share one interface:
  * MongoHistoryRepository — the production store (MongoDB / Atlas).
  * InMemoryHistoryRepository — process-local store used by unit tests
    (injected as a fixture) and available for local development via
    HISTORY_BACKEND=memory.

Database failures raise DatabaseUnavailable; the API layer translates
that into a clean 503 and never leaks driver exceptions.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger("backend.history")


class DatabaseUnavailable(Exception):
    """Raised when the history store cannot be reached or written."""


def build_record(*, request_id: str, endpoint: str, property_features: dict,
                 predicted_price_lacs: float, model_id: str) -> dict:
    return {"request_id": request_id,
            "timestamp": datetime.now(timezone.utc),
            "endpoint": endpoint,
            "property": property_features,
            "predicted_price_lacs": predicted_price_lacs,
            "currency": "INR",
            "model_id": model_id}


def serialize_record(record: dict) -> dict:
    out = dict(record)
    out.pop("_id", None)
    ts = out.get("timestamp")
    if isinstance(ts, datetime):
        out["timestamp"] = ts.isoformat()
    return out


class MongoHistoryRepository:
    def __init__(self, uri: str, db_name: str, collection: str,
                 timeout_ms: int = 1500):
        self._uri = uri
        self._db_name = db_name
        self._collection_name = collection
        self._timeout_ms = timeout_ms
        self._client = None
        self._available: bool | None = None

    def _collection(self):
        if self._client is None:
            from pymongo import MongoClient
            self._client = MongoClient(
                self._uri, serverSelectionTimeoutMS=self._timeout_ms,
                connectTimeoutMS=self._timeout_ms)
        return self._client[self._db_name][self._collection_name]

    def available(self) -> bool:
        if self._available is None:
            try:
                self._client_ok()
                self._available = True
            except Exception as exc:  # driver errors stay internal
                logger.warning("MongoDB unavailable: %s", exc)
                self._available = False
        return self._available

    def _client_ok(self) -> None:
        self._collection().database.client.admin.command("ping")

    def insert(self, record: dict) -> None:
        try:
            self._collection().insert_one(dict(record))
            self._available = True
        except Exception as exc:
            self._available = False
            raise DatabaseUnavailable(str(exc)) from exc

    def list(self, page: int, page_size: int) -> tuple[list[dict], int]:
        try:
            col = self._collection()
            total = col.count_documents({})
            cursor = (col.find({}).sort("timestamp", -1)
                      .skip((page - 1) * page_size).limit(page_size))
            return [serialize_record(r) for r in cursor], total
        except Exception as exc:
            raise DatabaseUnavailable(str(exc)) from exc

    def stats(self) -> dict:
        try:
            col = self._collection()
            prices = [d["predicted_price_lacs"]
                      for d in col.find({}, {"predicted_price_lacs": 1})]
            total = len(prices)
            return {"total_valuations": total,
                    "average_price_lacs": (sum(prices) / total) if total else None,
                    "min_price_lacs": min(prices) if prices else None,
                    "max_price_lacs": max(prices) if prices else None}
        except Exception as exc:
            raise DatabaseUnavailable(str(exc)) from exc


class InMemoryHistoryRepository:
    """Process-local store (tests / HISTORY_BACKEND=memory)."""

    def __init__(self):
        self._records: list[dict] = []

    def available(self) -> bool:
        return True

    def insert(self, record: dict) -> None:
        self._records.append(dict(record))

    def list(self, page: int, page_size: int) -> tuple[list[dict], int]:
        ordered = sorted(self._records, key=lambda r: r["timestamp"],
                         reverse=True)
        start = (page - 1) * page_size
        return ([serialize_record(r)
                 for r in ordered[start:start + page_size]],
                len(ordered))

    def stats(self) -> dict:
        prices = [r["predicted_price_lacs"] for r in self._records]
        total = len(prices)
        return {"total_valuations": total,
                "average_price_lacs": (sum(prices) / total) if total else None,
                "min_price_lacs": min(prices) if prices else None,
                "max_price_lacs": max(prices) if prices else None}
