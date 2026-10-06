"""API Gateway (HTTP API, payload format 2.0) adapter for VisionGuard.

Routes:
  POST /inspect  - base64-encoded image in the body, optional ?tenant=
  GET  /metrics  - gateway metering
  GET  /health   - liveness probe

Deployed as a second Lambda function sharing the VisionGuard container
image; only the CMD differs from the S3-triggered handler.
"""
import base64
import json
import os
import tempfile

from visionguard.agents.actor import ActorAgent
from visionguard.agents.detector import DetectorAgent
from visionguard.agents.reasoner import ReasonerAgent
from visionguard.gateway.policy import PolicyDenied, PolicyGateway
from visionguard.pipeline import run_pipeline

_gateway = PolicyGateway(audit_path="/tmp/audit.log")
_detector = DetectorAgent()
_reasoner = ReasonerAgent()
_actor = ActorAgent(quarantine_dir="/tmp/quarantine", audit=_gateway.audit)


def _response(status, body):
    return {"statusCode": status,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(body)}


def handler(event, context):
    http = event.get("requestContext", {}).get("http", {})
    method = http.get("method", "")
    path = http.get("path", "")

    if method == "GET" and path == "/health":
        return _response(200, {"status": "ok", "service": "visionguard"})
    if method == "GET" and path == "/metrics":
        return _response(200, _gateway.get_metrics())
    if method == "POST" and path == "/inspect":
        tenant = (event.get("queryStringParameters") or {}).get("tenant",
                                                                 "default")
        body = event.get("body") or ""
        try:
            raw = base64.b64decode(body) if event.get("isBase64Encoded") \
                else body.encode()
        except Exception:
            return _response(400, {"error": "body must be base64 image data"})
        with tempfile.NamedTemporaryFile(delete=False,
                                         suffix=".png") as tmp:
            tmp.write(raw)
            tmp_path = tmp.name
        try:
            result = run_pipeline(tmp_path, tenant=tenant,
                                  detector=_detector, reasoner=_reasoner,
                                  actor=_actor, gateway=_gateway)
        except PolicyDenied as exc:
            return _response(429, {"error": str(exc)})
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        return _response(200, result)
    return _response(404, {"error": "not found"})
