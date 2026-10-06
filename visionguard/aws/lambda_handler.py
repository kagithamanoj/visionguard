"""AWS Lambda handler: S3-triggered inspection.

Wiring (see infra/terraform):
  S3 incoming bucket --(ObjectCreated)--> this Lambda --writes-->
  S3 verdicts bucket (verdict JSON, keyed by source object name)
  S3 quarantine bucket (copy of the source image, only on quarantine action)

Because OpenCV is large, deploy this as a Lambda container image that
includes opencv-python-headless, torch, and the visionguard package.
Environment variables: VERDICTS_BUCKET, QUARANTINE_BUCKET, TENANT.
"""
import json
import os
import tempfile
import urllib.parse

import boto3

from visionguard.agents.actor import ActorAgent
from visionguard.agents.detector import DetectorAgent
from visionguard.agents.reasoner import ReasonerAgent
from visionguard.gateway.policy import PolicyDenied, PolicyGateway

s3 = boto3.client("s3")

VERDICTS_BUCKET = os.environ.get("VERDICTS_BUCKET", "")
QUARANTINE_BUCKET = os.environ.get("QUARANTINE_BUCKET", "")
TENANT = os.environ.get("TENANT", "default")

_gateway = PolicyGateway(audit_path="/tmp/audit.log")
_detector = DetectorAgent()
_reasoner = ReasonerAgent()
_actor = ActorAgent(quarantine_dir="/tmp/quarantine",
                    audit=_gateway.audit)

from visionguard.pipeline import run_pipeline  # noqa: E402


def _process_object(bucket: str, key: str) -> dict:
    key = urllib.parse.unquote_plus(key)
    suffix = os.path.splitext(key)[1] or ".png"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        local_path = tmp.name
    s3.download_file(bucket, key, local_path)
    try:
        result = run_pipeline(local_path, tenant=TENANT,
                              detector=_detector, reasoner=_reasoner,
                              actor=_actor, gateway=_gateway)
    except PolicyDenied as exc:
        return {"key": key, "denied": str(exc)}
    finally:
        if os.path.exists(local_path):
            os.unlink(local_path)

    verdict_key = os.path.splitext(key)[0] + ".verdict.json"
    if VERDICTS_BUCKET:
        s3.put_object(Bucket=VERDICTS_BUCKET, Key=verdict_key,
                      Body=json.dumps(result, indent=2).encode(),
                      ContentType="application/json")

    if "quarantine" in result["actions"].get("actions", []) and \
            QUARANTINE_BUCKET:
        s3.copy_object(Bucket=QUARANTINE_BUCKET,
                       Key=os.path.basename(key),
                       CopySource={"Bucket": bucket, "Key": key})

    return {"key": key, "verdict": result["verdict"]["severity"],
            "verdict_key": verdict_key}


def handler(event, context):
    results = []
    for record in event.get("Records", []):
        s3info = record.get("s3", {})
        bucket = s3info.get("bucket", {}).get("name", "")
        key = s3info.get("object", {}).get("key", "")
        if not bucket or not key:
            continue
        results.append(_process_object(bucket, key))
    return {"statusCode": 200, "results": results}
