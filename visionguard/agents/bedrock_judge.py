"""LLM judge backed by a real vision model on AWS Bedrock.

The judge is an optional second opinion on top of the rule-based verdict.
It is disabled by default. Nothing calls AWS unless it is explicitly
enabled, and the rule-based verdict stands on its own either way: the
judge never changes the severity, it only adds a note that records
whether it agreed or disagreed.

Enable it with environment variables:

    VISIONGUARD_LLM_JUDGE_ENABLED=true
    VISIONGUARD_BEDROCK_MODEL_ID=amazon.nova-lite-v1:0
    VISIONGUARD_BEDROCK_REGION=us-east-1

or pass ``enabled=True`` to ``BedrockJudge`` directly. The Lambda
inspect function reads the same variables, so the same switch works
locally and in AWS.

The model is called through the Bedrock Converse API with the plate
image and the classical detector findings. It must answer with one JSON
object: {"severity": ..., "confidence": ..., "note": ...}. Any response
that is not valid JSON, names a severity outside the known set, or
comes back as an AWS error is treated as "no second opinion" and the
judge returns None. Nothing is ever faked to fill the gap.
"""
import json
import os
import re
from typing import List, Optional

from .detector import Detection
from .reasoner import LLMJudge

SEVERITIES = ("none", "minor", "major", "critical")
DEFAULT_MODEL_ID = "amazon.nova-lite-v1:0"
DEFAULT_MAX_TOKENS = 300

_IMAGE_FORMATS = {".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg"}

SYSTEM_PROMPT = (
    "You are a quality-control inspector reviewing a photo of a metal "
    "plate for surface defects. Answer with one JSON object only, no "
    "other text."
)


def _prompt(detections: List[Detection]) -> str:
    if not detections:
        findings = "The classical detector found no defects."
    else:
        lines = []
        for d in detections:
            lines.append(
                f"- {d.label}: score {d.defect_score:.2f}, "
                f"area {d.area:.0f}, bbox {list(d.bbox)}")
        findings = "The classical detector found:\n" + "\n".join(lines)
    return (
        "Look at this plate image and judge its surface condition.\n"
        f"{findings}\n"
        "Reply with one JSON object with exactly these keys:\n"
        '  "severity": one of "none", "minor", "major", "critical"\n'
        '  "confidence": a number from 0.0 to 1.0\n'
        '  "note": one short sentence explaining what you see\n'
        "Judge from the image itself, not only from the detector list. "
        "A clean plate with no visible defects is \"none\"."
    )


def parse_judge_text(text: str, model_id: str) -> Optional[dict]:
    """Parse one model reply into an opinion dict, or None if invalid."""
    if not text or not isinstance(text, str):
        return None
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    severity = data.get("severity")
    if severity not in SEVERITIES:
        return None
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        return None
    note = data.get("note", "")
    if not isinstance(note, str):
        return None
    return {
        "severity": severity,
        "confidence": min(1.0, max(0.0, confidence)),
        "note": note.strip(),
        "model": model_id,
    }


class BedrockJudge(LLMJudge):
    """LLMJudge that calls a vision model through Bedrock Converse."""

    def __init__(self, enabled: bool = False,
                 model_id: str = DEFAULT_MODEL_ID,
                 region: Optional[str] = None,
                 max_tokens: int = DEFAULT_MAX_TOKENS,
                 client=None):
        self.enabled = bool(enabled)
        self.model_id = model_id or DEFAULT_MODEL_ID
        self.region = region
        self.max_tokens = int(max_tokens)
        self._client = client

    @classmethod
    def from_env(cls, enabled: Optional[bool] = None) -> "BedrockJudge":
        """Build a judge from environment variables.

        VISIONGUARD_LLM_JUDGE_ENABLED gates the judge. An explicit
        ``enabled`` argument overrides the variable.
        """
        if enabled is None:
            enabled = os.environ.get(
                "VISIONGUARD_LLM_JUDGE_ENABLED", "").strip().lower() in (
                    "1", "true", "yes", "on")
        model_id = os.environ.get("VISIONGUARD_BEDROCK_MODEL_ID",
                                  DEFAULT_MODEL_ID).strip() or DEFAULT_MODEL_ID
        region = (
            os.environ.get("VISIONGUARD_BEDROCK_REGION")
            or os.environ.get("AWS_REGION")
            or os.environ.get("AWS_DEFAULT_REGION")
            or None
        )
        try:
            max_tokens = int(os.environ.get(
                "VISIONGUARD_BEDROCK_MAX_TOKENS", DEFAULT_MAX_TOKENS))
        except ValueError:
            max_tokens = DEFAULT_MAX_TOKENS
        return cls(enabled=enabled, model_id=model_id,
                   region=region, max_tokens=max_tokens)

    @property
    def client(self):
        """Lazily build the bedrock-runtime client, only when enabled."""
        if self._client is None:
            import boto3
            self._client = boto3.client("bedrock-runtime",
                                        region_name=self.region)
        return self._client

    def judge(self, detections: List[Detection],
              image_path: str) -> Optional[dict]:
        if not self.enabled:
            return None
        if not image_path or not os.path.exists(image_path):
            return None
        suffix = os.path.splitext(image_path)[1].lower()
        image_format = _IMAGE_FORMATS.get(suffix)
        if image_format is None:
            return None
        try:
            with open(image_path, "rb") as f:
                image_bytes = f.read()
        except OSError:
            return None
        try:
            response = self.client.converse(
                modelId=self.model_id,
                system=[{"text": SYSTEM_PROMPT}],
                messages=[{
                    "role": "user",
                    "content": [
                        {"image": {"format": image_format,
                                   "source": {"bytes": image_bytes}}},
                        {"text": _prompt(detections)},
                    ],
                }],
                inferenceConfig={"maxTokens": self.max_tokens,
                                 "temperature": 0},
            )
        except Exception:
            return None
        texts = []
        try:
            content = response.get("output", {}).get("message", {}).get(
                "content", [])
            for block in content:
                if isinstance(block, dict) and "text" in block:
                    texts.append(block["text"])
        except (AttributeError, TypeError):
            return None
        return parse_judge_text("".join(texts), self.model_id)
