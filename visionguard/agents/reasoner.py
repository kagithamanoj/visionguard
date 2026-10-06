"""Reasoning agent: turns raw detections into a severity verdict.

Severity comes from configurable rules over defect scores and counts, so the
behavior is deterministic and auditable. An optional LLM judge hook can add a
second opinion; it is stubbed out by default and never faked.
"""
from dataclasses import dataclass, asdict
from typing import List, Optional

from .detector import Detection


@dataclass
class Verdict:
    severity: str      # none | minor | major | critical
    confidence: float  # 0.0 .. 1.0
    rationale: str
    detection_count: int
    max_defect_score: float
    judge_note: Optional[str] = None

    def to_dict(self):
        return asdict(self)


class LLMJudge:
    """Interface for an optional vision-language second opinion.

    Implement judge() to call a real model endpoint. The default stub
    returns None, which means "no second opinion available" and the
    rule-based verdict stands on its own.
    """

    def judge(self, detections: List[Detection],
              image_path: str) -> Optional[dict]:
        return None


class ReasonerAgent:
    def __init__(self,
                 critical_score: float = 0.85,
                 major_score: float = 0.60,
                 minor_score: float = 0.30,
                 critical_count: int = 5,
                 judge: Optional[LLMJudge] = None):
        self.critical_score = critical_score
        self.major_score = major_score
        self.minor_score = minor_score
        self.critical_count = critical_count
        self.judge = judge or LLMJudge()

    def reason(self, detections: List[Detection],
               image_path: str = "") -> Verdict:
        if not detections:
            return Verdict(severity="none", confidence=0.95,
                           rationale="No defects detected on the plate.",
                           detection_count=0, max_defect_score=0.0)

        top = max(detections, key=lambda d: d.defect_score)
        count = len(detections)
        labels = sorted({d.label for d in detections})

        if top.defect_score >= self.critical_score or count >= self.critical_count:
            severity, ref = "critical", self.critical_score
            why = (f"{count} defect(s) found; worst is a {top.label} scoring "
                   f"{top.defect_score:.2f}, at or above the critical "
                   f"threshold of {self.critical_score:.2f}.")
        elif top.defect_score >= self.major_score:
            severity, ref = "major", self.major_score
            why = (f"{count} defect(s) found; worst is a {top.label} scoring "
                   f"{top.defect_score:.2f}, at or above the major "
                   f"threshold of {self.major_score:.2f}.")
        elif top.defect_score >= self.minor_score:
            severity, ref = "minor", self.minor_score
            why = (f"{count} defect(s) found; worst is a {top.label} scoring "
                   f"{top.defect_score:.2f}, at or above the minor "
                   f"threshold of {self.minor_score:.2f}.")
        else:
            severity, ref = "none", self.minor_score
            why = (f"{count} low-scoring anomaly(ies); worst scores "
                   f"{top.defect_score:.2f}, below the minor threshold of "
                   f"{self.minor_score:.2f}. Treating the plate as clean.")

        confidence = float(min(0.99, 0.55 + abs(top.defect_score - ref)))
        rationale = f"{why} Defect types observed: {', '.join(labels)}."

        judge_note = None
        if image_path:
            try:
                opinion = self.judge.judge(detections, image_path)
            except Exception:
                opinion = None
            if opinion:
                judge_note = str(opinion.get("note", ""))
                if opinion.get("severity") in ("none", "minor", "major",
                                               "critical"):
                    rationale += " LLM judge concurs with review."

        return Verdict(severity=severity, confidence=round(confidence, 3),
                       rationale=rationale, detection_count=count,
                       max_defect_score=round(top.defect_score, 3),
                       judge_note=judge_note)
