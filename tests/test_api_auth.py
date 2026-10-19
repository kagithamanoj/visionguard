import json
import os

import pytest
from fastapi.testclient import TestClient

from visionguard.agents.actor import ActorAgent
from visionguard.gateway.policy import PolicyGateway, generate_api_key

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN_IMAGE = os.path.join(REPO_ROOT, "samples", "clean_000.png")


def _gw(tenant_cfg, tmp_path):
    return PolicyGateway(
        tenants={"t": tenant_cfg},
        audit_path=str(tmp_path / "audit.log"))


def _keyed_cfg(key="sekret-acme"):
    return {"requests_per_minute": 60, "min_confidence": 0.6,
            "allowed_actions": ["log"], "enabled": True, "api_key": key}


def _open_cfg():
    return {"requests_per_minute": 60, "min_confidence": 0.6,
            "allowed_actions": ["log"], "enabled": True}


def test_missing_key_rejected_before_metering(tmp_path):
    gw = _gw(_keyed_cfg(), tmp_path)
    allowed, reason = gw.check_request("t", None)
    assert allowed is False
    assert "API key" in reason
    # The key check runs before metering: rejected credentials never
    # touch the request counters.
    assert gw.get_metrics() == {}


def test_wrong_key_rejected_and_audited_without_leaking(tmp_path):
    gw = _gw(_keyed_cfg(), tmp_path)
    allowed, _ = gw.check_request("t", "nope")
    assert allowed is False
    entries = gw.audit_entries()
    rejected = [e for e in entries if e["type"] == "api_key_rejected"]
    assert len(rejected) == 1
    assert rejected[0]["tenant"] == "t"
    # The configured key value must never appear in the audit trail.
    assert not any("sekret-acme" in json.dumps(e) for e in entries)


def test_correct_key_passes_and_meters(tmp_path):
    gw = _gw(_keyed_cfg(), tmp_path)
    allowed, reason = gw.check_request("t", "sekret-acme")
    assert allowed is True
    assert reason == "ok"
    assert gw.get_metrics()["t"]["requests"] == 1


def test_tenant_without_key_stays_open(tmp_path):
    gw = _gw(_open_cfg(), tmp_path)
    assert gw.check_request("t", None)[0] is True
    assert gw.check_request("t", "anything")[0] is True


def test_rate_limit_still_applies_after_auth(tmp_path):
    gw = _gw({**_keyed_cfg(), "requests_per_minute": 1}, tmp_path)
    assert gw.check_request("t", "sekret-acme")[0] is True
    allowed, reason = gw.check_request("t", "sekret-acme")
    assert allowed is False
    assert "rate limit" in reason


def test_generate_api_key_is_unique_and_long():
    first, second = generate_api_key(), generate_api_key()
    assert first != second
    assert len(first) >= 43


def test_from_env_loads_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("VISIONGUARD_API_KEYS",
                       json.dumps({"acme": "k1"}))
    gw = PolicyGateway.from_env(audit_path=str(tmp_path / "audit.log"))
    assert gw.check_request("acme", "k1")[0] is True
    assert gw.check_request("acme", "wrong")[0] is False
    # Tenants without a configured key keep working unauthenticated.
    assert gw.check_request("default", None)[0] is True


def test_from_env_rejects_invalid_json(monkeypatch):
    monkeypatch.setenv("VISIONGUARD_API_KEYS", "{not json")
    with pytest.raises(ValueError):
        PolicyGateway.from_env()


def test_from_env_rejects_non_object_json(monkeypatch):
    monkeypatch.setenv("VISIONGUARD_API_KEYS", '["a", "b"]')
    with pytest.raises(ValueError):
        PolicyGateway.from_env()


def _api_gateway(tmp_path):
    tenants = {
        "acme": {**_open_cfg(), "api_key": "test-key-acme",
                 "allowed_actions": ["log", "quarantine", "alert"]},
        "beta": {**_open_cfg(), "api_key": "test-key-beta",
                 "allowed_actions": ["log", "quarantine", "alert"]},
        "default": _open_cfg(),
    }
    return PolicyGateway(tenants=tenants,
                         audit_path=str(tmp_path / "audit.log"))


@pytest.fixture()
def api_client(tmp_path, monkeypatch):
    import visionguard.api as api_mod
    gw = _api_gateway(tmp_path)
    monkeypatch.setattr(api_mod, "_gateway", gw)
    monkeypatch.setattr(api_mod, "_actor", ActorAgent(audit=gw.audit))
    return TestClient(api_mod.app)


@pytest.fixture()
def open_client(tmp_path, monkeypatch):
    import visionguard.api as api_mod
    gw = PolicyGateway(tenants={"default": _open_cfg()},
                       audit_path=str(tmp_path / "audit.log"))
    monkeypatch.setattr(api_mod, "_gateway", gw)
    monkeypatch.setattr(api_mod, "_actor", ActorAgent(audit=gw.audit))
    return TestClient(api_mod.app)


def _inspect(client, tenant="acme", key="test-key-acme"):
    headers = {"X-API-Key": key} if key is not None else {}
    with open(CLEAN_IMAGE, "rb") as f:
        return client.post("/inspect", params={"tenant": tenant},
                           files={"image": ("clean_000.png", f, "image/png")},
                           headers=headers)


def test_inspect_requires_key(api_client):
    resp = _inspect(api_client, key=None)
    assert resp.status_code == 401


def test_inspect_rejects_wrong_key(api_client):
    resp = _inspect(api_client, key="wrong")
    assert resp.status_code == 401
    assert resp.headers.get("WWW-Authenticate") == "ApiKey"


def test_inspect_rejects_other_tenants_key(api_client):
    # beta's key does not authenticate the acme tenant.
    resp = _inspect(api_client, tenant="beta", key="test-key-acme")
    assert resp.status_code == 401


def test_inspect_accepts_valid_key(api_client):
    resp = _inspect(api_client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["tenant"] == "acme"
    assert "verdict" in body
    assert "detections" in body


def test_metrics_requires_key_and_is_tenant_scoped(api_client):
    assert api_client.get("/metrics",
                          params={"tenant": "acme"}).status_code == 401
    assert _inspect(api_client).status_code == 200
    resp = api_client.get("/metrics", params={"tenant": "acme"},
                          headers={"X-API-Key": "test-key-acme"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["tenant"] == "acme"
    assert body["metrics"]["requests"] == 1
    # No other tenant's metering leaks through this tenant's key.
    assert "beta" not in resp.text


def test_health_stays_open(api_client):
    resp = api_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_no_keys_configured_means_no_auth(open_client):
    resp = _inspect(open_client, tenant="default", key=None)
    assert resp.status_code == 200
