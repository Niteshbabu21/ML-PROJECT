#!/usr/bin/env python3
"""services/token_service.py — prototype fractional token supply.

Rule (from the project architecture, unchanged): one token represents
₹10,000 of property value; the supply is the FLOOR of
value_inr / denomination, so issued tokens never exceed the valuation.
The remainder is reported explicitly as rounding information.

This is an academic prototype calculation. It performs no blockchain
interaction and creates no legal claim on any property.
"""
from __future__ import annotations

import math


def calculate_token_supply(valuation_lacs: float,
                           denomination_inr: int = 10000) -> dict:
    if valuation_lacs is None or float(valuation_lacs) <= 0:
        raise ValueError("valuation_lacs must be a positive number")
    value_inr = round(float(valuation_lacs) * 100_000, 2)
    exact = value_inr / denomination_inr
    supply = math.floor(exact)
    remainder_inr = round(value_inr - supply * denomination_inr, 2)
    return {"valuation_lacs": round(float(valuation_lacs), 2),
            "valuation_inr": value_inr,
            "currency": "INR",
            "token_denomination_inr": denomination_inr,
            "token_supply": supply,
            "exact_token_amount": round(exact, 6),
            "rounding": {"method": "floor",
                         "remainder_inr": remainder_inr,
                         "note": "Supply is floored so tokens issued "
                                 "never exceed the valuation; the "
                                 "remainder stays untokenised."},
            "prototype_note": "Academic prototype calculation only — "
                              "not an on-chain issuance and not legal "
                              "proof of ownership."}
