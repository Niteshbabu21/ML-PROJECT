#!/usr/bin/env python3
"""services/history_service.py — dashboard history & summary use cases."""
from __future__ import annotations

from errors import ApiError  # noqa: E402
from models.history import DatabaseUnavailable  # noqa: E402


class HistoryService:
    def __init__(self, repository):
        self._repo = repository

    def _guard(self, fn):
        try:
            return fn()
        except DatabaseUnavailable:
            raise ApiError(503, "DATABASE_UNAVAILABLE",
                           "Valuation history is temporarily unavailable.")

    def list_history(self, page: int, page_size: int) -> dict:
        items, total = self._guard(lambda: self._repo.list(page, page_size))
        pages = (total + page_size - 1) // page_size if total else 0
        return {"items": items,
                "pagination": {"page": page, "page_size": page_size,
                               "total": total, "pages": pages}}

    def summary(self) -> dict:
        stats = self._guard(self._repo.stats)
        stats["database_connected"] = bool(self._repo.available())
        return stats
