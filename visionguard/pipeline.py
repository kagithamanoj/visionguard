"""VisionGuard pipeline: detect -> reason -> act, gated by policy at each step.

Every request goes through the policy gateway first (rate limit), then the
detection and reasoning agents run, then the verdict is re-checked against
confidence thresholds and the action allow-list before the action agent
fires. Nothing acts without passing the gate.
"""
import argparse
import json
import time
from dataclasses import replace

from .agents.actor import ActorAgent
from .agents.detector import DetectorAgent
from .agents.reasoner import ReasonerAgent
from .gateway.policy import PolicyDenied, PolicyGateway


def build(tenant_config: dict = None, **kwargs):
    gateway = PolicyGateway(tenants=tenant_config, **kwargs) \
        if tenant_config else PolicyGateway(**kwargs)
    detector = DetectorAgent()
    reasoner = ReasonerAgent()
    actor = ActorAgent(audit=gateway.audit)
    return detector, reasoner, actor, gateway


def run_pipeline(image_path: str,
                 tenant: str = "default",
                 detector: DetectorAgent = None,
                 reasoner: ReasonerAgent = None,
                 actor: ActorAgent = None,
                 gateway: PolicyGateway = None) -> dict:
    detector = detector or DetectorAgent()
    reasoner = reasoner or ReasonerAgent()
    gateway = gateway or PolicyGateway()
    actor = actor or ActorAgent(audit=gateway.audit)

    started = time.monotonic()
    allowed, reason = gateway.check_request(tenant)
    if not allowed:
        raise PolicyDenied(f"request denied for tenant '{tenant}': {reason}")

    detections = detector.detect(image_path)
    verdict = reasoner.reason(detections, image_path)

    effective, note = gateway.check_verdict(tenant, verdict)
    if effective != verdict.severity:
        verdict = replace(verdict, severity=effective,
                          rationale=verdict.rationale + " " + note)

    actions = actor.act(image_path, verdict, tenant=tenant)
    latency_ms = (time.monotonic() - started) * 1000.0
    gateway.record_result(tenant, verdict.severity, latency_ms)

    return {
        "image": image_path,
        "tenant": tenant,
        "detections": [d.to_dict() for d in detections],
        "verdict": verdict.to_dict(),
        "actions": actions,
        "latency_ms": round(latency_ms, 2),
    }


def main():
    p = argparse.ArgumentParser(description="VisionGuard inspection pipeline")
    p.add_argument("--image", required=True, help="path to the plate image")
    p.add_argument("--tenant", default="default")
    p.add_argument("--audit", default="audit.log")
    a = p.parse_args()
    gateway = PolicyGateway(audit_path=a.audit)
    try:
        result = run_pipeline(a.image, tenant=a.tenant, gateway=gateway)
    except PolicyDenied as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        raise SystemExit(2)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
