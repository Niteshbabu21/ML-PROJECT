#!/usr/bin/env python3
"""test_api.py — pytest suite for the Flask backend.

Uses the Flask test client with a controlled fixture: the REAL packaged
model and the REAL risk engine, with only the external dependency —
MongoDB — replaced by an in-memory repository injected into the app
factory (mocking external services is confined to tests, per design).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app import create_app  # noqa: E402
from config import TestConfig  # noqa: E402
from models.history import InMemoryHistoryRepository  # noqa: E402

PROPERTY = {"POSTED_BY": "Owner", "UNDER_CONSTRUCTION": 0, "RERA": 1,
            "BHK_NO.": 3, "BHK_OR_RK": "BHK", "SQUARE_FT": 1200.0,
            "RESALE": 0, "CITY": "Bangalore", "LOCALITY": "Koramangala",
            "LATITUDE": 12.935, "LONGITUDE": 77.624,
            "SQUARE_FT_PER_BHK": 400.0, "LOG_SQUARE_FT": 7.09,
            "DIST_TO_CITY_CENTROID": 3.2, "CITY_FREQ": 3298.0,
            "LOCALITY_FREQ": 450.0, "SQFT_BAND": "M", "BHK_CONFIG": "3BHK",
            "GEO_CLUSTER": "C04", "LAT_LON_INTERACTION": 1003.4}


@pytest.fixture(scope="module")
def client():
    from models.chain_store import InMemoryChainStore
    app = create_app(TestConfig,
                     history_repository=InMemoryHistoryRepository(),
                     chain_store=InMemoryChainStore())
    return app.test_client()


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert data["model_loaded"] is True
    assert data["database_connected"] is True
    assert data["status"] == "ok"


def test_predict_success_and_envelope(client):
    r = client.post("/api/valuation/predict", json={"property": PROPERTY})
    assert r.status_code == 200
    body = r.get_json()
    assert body["success"] is True and body["request_id"]
    data = body["data"]
    assert data["predicted_price_lacs"] > 0
    assert data["currency"] == "INR"
    assert data["model_id"] == "xgboost-e01"
    assert data["history_saved"] is True
    assert r.headers.get("X-Request-ID")


def test_predict_invalid_feature_value(client):
    bad = dict(PROPERTY, SQUARE_FT=0)
    r = client.post("/api/valuation/predict", json={"property": bad})
    assert r.status_code == 400
    err = r.get_json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert "SQUARE_FT" in err["message"]


def test_predict_missing_feature(client):
    incomplete = {k: v for k, v in PROPERTY.items() if k != "LOCALITY"}
    r = client.post("/api/valuation/predict", json={"property": incomplete})
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_predict_non_json_body(client):
    r = client.post("/api/valuation/predict", data="not json",
                    content_type="text/plain")
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == "INVALID_JSON"


def test_explain(client):
    r = client.post("/api/valuation/explain", json={"property": PROPERTY})
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert len(data["contributions"]) == 20
    assert len(data["top_influential"]) == 5
    assert data["additivity"]["verified"] is True
    assert data["prediction"]["predicted_price_lacs"] > 0
    assert data["base_value_log"] > 0


def test_risk_assess_with_provided_price(client):
    r = client.post("/api/risk/assess",
                    json={"property": PROPERTY, "predicted_price_lacs": 85.0})
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert data["risk_category"] in {"LOW", "MEDIUM", "HIGH"}
    assert 0 <= data["risk_score"] <= 100
    assert len(data["factors"]) == 7
    assert set(data["domains"]) == {"regulatory_construction",
                                    "data_quality", "model_uncertainty"}
    assert data["predicted_price_source"] == "provided"


def test_risk_assess_auto_price(client):
    r = client.post("/api/risk/assess", json={"property": PROPERTY})
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert data["predicted_price_source"] == "computed_by_valuation_model"
    assert data["predicted_price_lacs"] > 0


def test_token_from_valuation_lacs(client):
    r = client.post("/api/token/calculate", json={"valuation_lacs": 85.37})
    assert r.status_code == 200
    data = r.get_json()["data"]
    # ₹85.37L = ₹8,537,000 -> floor(/10000) = 853 tokens, ₹7,000 remainder
    assert data["token_supply"] == 853
    assert data["token_denomination_inr"] == 10000
    assert data["rounding"]["remainder_inr"] == 7000.0
    assert data["rounding"]["method"] == "floor"


def test_token_from_property(client):
    r = client.post("/api/token/calculate", json={"property": PROPERTY})
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert data["token_supply"] > 0
    assert data["valuation_source"] == "computed_by_valuation_model"


def test_token_missing_input(client):
    r = client.post("/api/token/calculate", json={})
    assert r.status_code == 400


def test_model_metrics(client):
    r = client.get("/api/models/metrics")
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert data["model_id"] == "xgboost-e01"
    assert abs(data["metrics"]["test"]["r2"] - 0.7423) < 0.001


def test_model_compare(client):
    r = client.get("/api/models/compare")
    assert r.status_code == 200
    entries = r.get_json()["data"]["comparison"]
    assert len(entries) >= 5
    selected = [e for e in entries if e.get("selected")]
    assert len(selected) == 1
    assert "optimisation" in selected[0]["model"]


def test_model_schema(client):
    r = client.get("/api/models/schema")
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert len(data["feature_order"]) == 20
    assert data["target"]["transform"] == "log1p"


def test_shap_summary(client):
    r = client.get("/api/models/shap-summary")
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert len(data["ranking"]) == 20
    assert data["ranking"][0]["feature"] == "SQUARE_FT"
    assert data["sample_size"] == 2000


def test_dashboard_history_pagination(client):
    for _ in range(3):
        client.post("/api/valuation/predict", json={"property": PROPERTY})
    r = client.get("/api/dashboard/history?page=1&page_size=2")
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert data["pagination"]["total"] >= 3
    assert len(data["items"]) == 2
    assert data["pagination"]["pages"] >= 2
    item = data["items"][0]
    assert item["currency"] == "INR" and item["model_id"] == "xgboost-e01"
    r2 = client.get("/api/dashboard/history?page=2&page_size=2")
    assert len(r2.get_json()["data"]["items"]) >= 1


def test_dashboard_summary(client):
    r = client.get("/api/dashboard/summary")
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert data["total_valuations"] >= 3
    assert data["average_price_lacs"] > 0
    assert data["database_connected"] is True


class FailingRepository:
    """Simulates an unreachable MongoDB (mocking is confined to tests)."""

    def available(self):
        return False

    def insert(self, record):
        from models.history import DatabaseUnavailable
        raise DatabaseUnavailable("simulated outage")

    def list(self, page, page_size):
        from models.history import DatabaseUnavailable
        raise DatabaseUnavailable("simulated outage")

    def stats(self):
        from models.history import DatabaseUnavailable
        raise DatabaseUnavailable("simulated outage")


@pytest.fixture(scope="module")
def degraded_client():
    app = create_app(TestConfig, history_repository=FailingRepository())
    return app.test_client()


def test_predict_survives_database_outage(degraded_client):
    r = degraded_client.post("/api/valuation/predict",
                             json={"property": PROPERTY})
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert data["predicted_price_lacs"] > 0
    assert data["history_saved"] is False


def test_history_clean_503_on_database_outage(degraded_client):
    r = degraded_client.get("/api/dashboard/history")
    assert r.status_code == 503
    assert r.get_json()["error"]["code"] == "DATABASE_UNAVAILABLE"
    h = degraded_client.get("/api/health")
    assert h.get_json()["data"]["status"] == "degraded"


def test_admin_key_protects_chain_writes():
    class AdminConfig(TestConfig):
        ADMIN_API_KEY = "test-admin-key"
    from models.chain_store import InMemoryChainStore
    app = create_app(AdminConfig,
                     history_repository=InMemoryHistoryRepository(),
                     chain_store=InMemoryChainStore())
    c = app.test_client()
    r = c.post("/api/chain/register", json={"property": PROPERTY})
    assert r.status_code == 401
    assert r.get_json()["error"]["code"] == "ADMIN_UNAUTHORIZED"
    r = c.post("/api/chain/register", json={"property": PROPERTY},
               headers={"X-Admin-Key": "wrong"})
    assert r.status_code == 401
    # Correct key passes the auth gate (then fails on the absent chain,
    # proving the request got through authorisation).
    r = c.post("/api/chain/register", json={"property": PROPERTY},
               headers={"X-Admin-Key": "test-admin-key"})
    assert r.status_code == 503
    assert r.get_json()["error"]["code"] == "CHAIN_UNAVAILABLE"
    # Reads stay public.
    assert c.get("/api/chain/status").status_code == 200


def test_production_refuses_default_secret_key():
    class ProdConfig(TestConfig):
        ENV = "production"
    from models.chain_store import InMemoryChainStore
    with pytest.raises(RuntimeError):
        create_app(ProdConfig,
                   history_repository=InMemoryHistoryRepository(),
                   chain_store=InMemoryChainStore())


def test_model_loading_failure_degrades_gracefully(tmp_path):
    """A missing/corrupt model artifact must not crash the app: health
    reports the failure and valuation returns a clean 503."""
    from services.ml_service import MLService
    from models.chain_store import InMemoryChainStore
    bad_ml = MLService(tmp_path)  # empty directory: no model.pkl inside
    bad_ml.load()
    assert bad_ml.loaded is False and bad_ml.load_error
    app = create_app(TestConfig,
                     history_repository=InMemoryHistoryRepository(),
                     chain_store=InMemoryChainStore(), ml_service=bad_ml)
    client = app.test_client()
    health = client.get("/api/health").get_json()["data"]
    assert health["model_loaded"] is False
    assert health["status"] == "degraded"
    r = client.post("/api/valuation/predict", json={"property": PROPERTY})
    assert r.status_code == 503
    assert r.get_json()["error"]["code"] == "MODEL_UNAVAILABLE"


def test_chain_status_reports_unavailable_without_node(client):
    r = client.get("/api/chain/status")
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert data["connected"] is False  # no Hardhat node runs during tests
    assert data["rpc_url"].startswith("http")


def test_chain_register_503_without_node(client):
    r = client.post("/api/chain/register", json={"property": PROPERTY})
    assert r.status_code == 503
    assert r.get_json()["error"]["code"] == "CHAIN_UNAVAILABLE"


def test_chain_properties_empty(client):
    r = client.get("/api/chain/properties")
    assert r.status_code == 200
    assert r.get_json()["data"]["properties"] == []


def test_chain_mint_validation(client):
    r = client.post("/api/chain/mint", json={"chain_property_id": "x"})
    assert r.status_code == 400


def test_unknown_route_envelope(client):
    r = client.get("/api/nope")
    assert r.status_code == 404
    body = r.get_json()
    assert body["success"] is False
    assert body["error"]["code"] == "NOT_FOUND"


def test_method_not_allowed_envelope(client):
    r = client.get("/api/valuation/predict")
    assert r.status_code == 405
    assert r.get_json()["error"]["code"] == "METHOD_NOT_ALLOWED"
