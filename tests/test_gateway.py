from visionguard.agents.detector import Detection
from visionguard.agents.reasoner import ReasonerAgent, Verdict
from visionguard.gateway.policy import PolicyDenied, PolicyGateway


def _gw(tenant_cfg, tmp_path):
    return PolicyGateway(
        tenants={"t": tenant_cfg},
        audit_path=str(tmp_path / "audit.log"))


def test_rate_limit_blocks_over_limit(tmp_path):
    gw = _gw({"requests_per_minute": 2, "min_confidence": 0.6,
              "allowed_actions": ["log"], "enabled": True}, tmp_path)
    assert gw.check_request("t")[0] is True
    assert gw.check_request("t")[0] is True
    allowed, reason = gw.check_request("t")
    assert allowed is False
    assert "rate limit" in reason
    assert gw.get_metrics()["t"]["denied"] == 1


def test_disabled_tenant_denied(tmp_path):
    gw = _gw({"requests_per_minute": 60, "min_confidence": 0.6,
              "allowed_actions": ["log"], "enabled": False}, tmp_path)
    allowed, reason = gw.check_request("t")
    assert allowed is False
    assert "disabled" in reason


def test_low_confidence_verdict_held_for_review(tmp_path):
    gw = _gw({"requests_per_minute": 60, "min_confidence": 0.9,
              "allowed_actions": ["log", "quarantine", "alert"],
              "enabled": True}, tmp_path)
    verdict = Verdict(severity="major", confidence=0.65,
                      rationale="test", detection_count=1,
                      max_defect_score=0.65)
    effective, note = gw.check_verdict("t", verdict)
    assert effective == "review"
    assert "held for review" in note


def test_critical_downgraded_when_alert_not_allowed(tmp_path):
    gw = _gw({"requests_per_minute": 60, "min_confidence": 0.5,
              "allowed_actions": ["log", "quarantine"],
              "enabled": True}, tmp_path)
    verdict = Verdict(severity="critical", confidence=0.95,
                      rationale="test", detection_count=2,
                      max_defect_score=0.95)
    effective, _ = gw.check_verdict("t", verdict)
    assert effective == "major"


def test_audit_log_records_decisions(tmp_path):
    gw = _gw({"requests_per_minute": 1, "min_confidence": 0.6,
              "allowed_actions": ["log"], "enabled": True}, tmp_path)
    gw.check_request("t")
    gw.check_request("t")  # denied
    types = [e["type"] for e in gw.audit_entries()]
    assert "request_allowed" in types
    assert "request_denied" in types


def test_metering_counts_requests(tmp_path):
    gw = _gw({"requests_per_minute": 60, "min_confidence": 0.6,
              "allowed_actions": ["log"], "enabled": True}, tmp_path)
    gw.check_request("t")
    gw.record_result("t", "major", 12.5)
    m = gw.get_metrics()["t"]
    assert m["requests"] == 1
    assert m["by_severity"] == {"major": 1}
    assert m["avg_latency_ms"] == 12.5
