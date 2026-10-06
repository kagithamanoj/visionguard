import json
import os

import pytest

from make_sample_images import generate
from visionguard.agents.actor import ActorAgent
from visionguard.agents.detector import DetectorAgent
from visionguard.agents.reasoner import ReasonerAgent
from visionguard.gateway.policy import PolicyDenied, PolicyGateway
from visionguard.pipeline import run_pipeline


@pytest.fixture(scope="module")
def sample_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("samples")
    generate(3, str(d), seed=999)
    return d


def _components(tmp_path):
    audit_path = str(tmp_path / "audit.log")
    quarantine_dir = str(tmp_path / "quarantine")
    gateway = PolicyGateway(audit_path=audit_path)
    actor = ActorAgent(quarantine_dir=quarantine_dir, audit=gateway.audit)
    return (DetectorAgent(), ReasonerAgent(), actor, gateway,
            audit_path, quarantine_dir)


def test_pipeline_defective_end_to_end(sample_dir, tmp_path):
    detector, reasoner, actor, gateway, audit_path, qdir = _components(tmp_path)
    img = os.path.join(sample_dir, "defective_scratch_000.png")
    result = run_pipeline(img, detector=detector, reasoner=reasoner,
                          actor=actor, gateway=gateway)
    assert result["verdict"]["severity"] in ("minor", "major", "critical")
    assert result["verdict"]["detection_count"] > 0
    assert "quarantine" in result["actions"]["actions"]
    assert os.path.exists(result["actions"]["quarantine_path"])
    # original image untouched
    assert os.path.exists(img)
    # audit trail exists
    entries = gateway.audit_entries()
    assert any(e["type"] == "action" for e in entries)
    assert any(e["type"] == "request_allowed" for e in entries)


def test_pipeline_clean_plate_no_action(sample_dir, tmp_path):
    detector, reasoner, actor, gateway, audit_path, qdir = _components(tmp_path)
    img = os.path.join(sample_dir, "clean_000.png")
    result = run_pipeline(img, detector=detector, reasoner=reasoner,
                          actor=actor, gateway=gateway)
    assert result["verdict"]["severity"] == "none"
    assert result["actions"]["actions"] == []
    assert not os.path.exists(qdir) or os.listdir(qdir) == []


def test_pipeline_denied_when_rate_limited(sample_dir, tmp_path):
    gateway = PolicyGateway(
        tenants={"default": {"requests_per_minute": 1,
                             "min_confidence": 0.6,
                             "allowed_actions": ["log"],
                             "enabled": True}},
        audit_path=str(tmp_path / "audit.log"))
    img = os.path.join(sample_dir, "clean_000.png")
    run_pipeline(img, gateway=gateway)  # consumes the one token
    with pytest.raises(PolicyDenied):
        run_pipeline(img, gateway=gateway)


def test_pipeline_low_confidence_held(sample_dir, tmp_path):
    gateway = PolicyGateway(
        tenants={"default": {"requests_per_minute": 60,
                             "min_confidence": 0.99,
                             "allowed_actions": ["log", "quarantine",
                                                 "alert"],
                             "enabled": True}},
        audit_path=str(tmp_path / "audit.log"))
    detector, reasoner = DetectorAgent(), ReasonerAgent()
    actor = ActorAgent(quarantine_dir=str(tmp_path / "q"),
                       audit=gateway.audit)
    img = os.path.join(sample_dir, "defective_dent_001.png")
    result = run_pipeline(img, detector=detector, reasoner=reasoner,
                          actor=actor, gateway=gateway)
    assert result["verdict"]["severity"] == "review"
    assert result["actions"]["actions"] == ["log"]
