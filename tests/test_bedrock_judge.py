import json
import os

import pytest

from make_sample_images import generate
from visionguard.agents.bedrock_judge import (
    BedrockJudge, parse_judge_text)
from visionguard.agents.detector import Detection
from visionguard.agents.reasoner import LLMJudge, ReasonerAgent
from visionguard.pipeline import run_pipeline


class FakeBedrockClient:
    """Stand-in for the boto3 bedrock-runtime client."""

    def __init__(self, reply_text=None, error=None):
        self.reply_text = reply_text
        self.error = error
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return {"output": {"message": {"content": [
            {"text": self.reply_text}]}}}


@pytest.fixture(scope="module")
def sample_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("samples")
    generate(2, str(d), seed=999)
    return d


def _sample_image(sample_dir):
    for name in sorted(os.listdir(sample_dir)):
        if name.endswith(".png"):
            return os.path.join(sample_dir, name)
    raise AssertionError("no sample image generated")


def _detections():
    return [Detection(bbox=(0, 0, 10, 10), area=100.0,
                      defect_score=0.9, label="scratch")]


def test_disabled_judge_never_calls_bedrock(sample_dir):
    client = FakeBedrockClient(reply_text="{}")
    judge = BedrockJudge(enabled=False, client=client)
    assert judge.judge(_detections(), _sample_image(sample_dir)) is None
    assert client.calls == []


def test_enabled_judge_parses_opinion(sample_dir):
    reply = json.dumps({"severity": "major", "confidence": 0.8,
                        "note": "A long scratch crosses the plate."})
    client = FakeBedrockClient(reply_text=reply)
    judge = BedrockJudge(enabled=True, model_id="test-model",
                         client=client)
    opinion = judge.judge(_detections(), _sample_image(sample_dir))
    assert opinion["severity"] == "major"
    assert opinion["confidence"] == 0.8
    assert "scratch" in opinion["note"]
    assert opinion["model"] == "test-model"
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["modelId"] == "test-model"
    assert call["messages"][0]["content"][0]["image"]["format"] == "png"


def test_judge_returns_none_on_non_json_reply(sample_dir):
    client = FakeBedrockClient(reply_text="looks bad to me")
    judge = BedrockJudge(enabled=True, client=client)
    assert judge.judge(_detections(), _sample_image(sample_dir)) is None


def test_judge_returns_none_on_invalid_severity(sample_dir):
    reply = json.dumps({"severity": "catastrophic", "confidence": 0.9,
                        "note": "Bad."})
    client = FakeBedrockClient(reply_text=reply)
    judge = BedrockJudge(enabled=True, client=client)
    assert judge.judge(_detections(), _sample_image(sample_dir)) is None


def test_judge_returns_none_on_bedrock_error(sample_dir):
    client = FakeBedrockClient(error=RuntimeError("throttled"))
    judge = BedrockJudge(enabled=True, client=client)
    assert judge.judge(_detections(), _sample_image(sample_dir)) is None


def test_judge_returns_none_for_unsupported_image_format(tmp_path):
    path = str(tmp_path / "image.gif")
    with open(path, "wb") as f:
        f.write(b"not a real image")
    client = FakeBedrockClient(reply_text="{}")
    judge = BedrockJudge(enabled=True, client=client)
    assert judge.judge(_detections(), path) is None
    assert client.calls == []


def test_from_env_reads_gate_and_model(monkeypatch):
    monkeypatch.setenv("VISIONGUARD_LLM_JUDGE_ENABLED", "true")
    monkeypatch.setenv("VISIONGUARD_BEDROCK_MODEL_ID", "env-model")
    monkeypatch.setenv("VISIONGUARD_BEDROCK_REGION", "us-west-2")
    judge = BedrockJudge.from_env()
    assert judge.enabled is True
    assert judge.model_id == "env-model"
    assert judge.region == "us-west-2"


def test_from_env_defaults_to_disabled(monkeypatch):
    monkeypatch.delenv("VISIONGUARD_LLM_JUDGE_ENABLED", raising=False)
    monkeypatch.delenv("VISIONGUARD_BEDROCK_MODEL_ID", raising=False)
    judge = BedrockJudge.from_env()
    assert judge.enabled is False
    assert judge.model_id == "amazon.nova-lite-v1:0"


def test_parse_judge_text_extracts_json_from_prose():
    text = 'Here is my review: {"severity": "minor", "confidence": 0.6, "note": "Small mark."} done.'
    opinion = parse_judge_text(text, "m")
    assert opinion["severity"] == "minor"
    assert opinion["confidence"] == 0.6


class _FixedJudge(LLMJudge):
    def __init__(self, opinion):
        self._opinion = opinion

    def judge(self, detections, image_path):
        return dict(self._opinion)


def test_reasoner_notes_agreement():
    reasoner = ReasonerAgent(judge=_FixedJudge(
        {"severity": "critical", "note": "Severe scratch."}))
    verdict = reasoner.reason(_detections(), "some/image.png")
    assert verdict.severity == "critical"
    assert verdict.judge_note == "Severe scratch."
    assert "agrees" in verdict.rationale


def test_reasoner_notes_disagreement_but_keeps_rule_verdict():
    reasoner = ReasonerAgent(judge=_FixedJudge(
        {"severity": "minor", "note": "Looks small to me.",
         "model": "test-model"}))
    verdict = reasoner.reason(_detections(), "some/image.png")
    assert verdict.severity == "critical"
    assert verdict.judge_note == "[test-model] Looks small to me."
    assert "disagrees" in verdict.rationale
    assert "rule-based verdict stands" in verdict.rationale


def test_pipeline_with_bedrock_judge_records_note(sample_dir, tmp_path):
    from visionguard.agents.actor import ActorAgent
    from visionguard.gateway.policy import PolicyGateway
    reply = json.dumps({"severity": "major", "confidence": 0.8,
                        "note": "Scratch visible."})
    judge = BedrockJudge(enabled=True, model_id="test-model",
                         client=FakeBedrockClient(reply_text=reply))
    gateway = PolicyGateway(audit_path=str(tmp_path / "audit.log"))
    actor = ActorAgent(quarantine_dir=str(tmp_path / "q"),
                       audit=gateway.audit)
    img = os.path.join(sample_dir, "defective_scratch_000.png")
    result = run_pipeline(img, reasoner=ReasonerAgent(judge=judge),
                          actor=actor, gateway=gateway)
    assert result["verdict"]["judge_note"] is not None
    assert "Scratch visible" in result["verdict"]["judge_note"]
