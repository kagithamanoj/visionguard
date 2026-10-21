"""Best-effort CloudWatch custom metrics for the inspect Lambda.

Namespace: VisionGuard/Inspection. Metrics published:
  VerdictCount         (Count, dims: Verdict, Tenant) one per finished
                        inspection, valued 1 so the dashboard can sum a
                        verdict mix (none | minor | major | critical).
  GatewayDenial        (Count, dims: Reason, Tenant) one per PolicyDenied
                        raised in the Lambda handler.
  InspectionLatencyMs  (Milliseconds, dim: Tenant) the pipeline latency of
                        a finished inspection.

Publishing is opt-in via VISIONGUARD_METRICS_ENABLED=true (the Terraform
stack sets it on the inspect Lambda). Failures are swallowed and logged
to stderr: a broken metric must never break an inspection.
"""
import os
import sys

import boto3

NAMESPACE = "VisionGuard/Inspection"


class MetricsPublisher:
    """Thin wrapper around cloudwatch:PutMetricData with an off switch."""

    def __init__(self, enabled=False, client=None,
                 namespace=NAMESPACE):
        self.enabled = enabled
        self.namespace = namespace
        self._client = client

    @classmethod
    def from_env(cls, env_var="VISIONGUARD_METRICS_ENABLED", env=None):
        env = env if env is not None else os.environ
        enabled = str(env.get(env_var, "")).lower() == "true"
        return cls(enabled=enabled)

    def _cloudwatch(self):
        if self._client is None:
            self._client = boto3.client("cloudwatch")
        return self._client

    def put(self, metric_name, value, unit="Count", dimensions=None):
        """Publish one metric datum. No-op when disabled; never raises."""
        if not self.enabled:
            return
        try:
            self._cloudwatch().put_metric_data(
                Namespace=self.namespace,
                MetricData=[{
                    "MetricName": metric_name,
                    "Value": float(value),
                    "Unit": unit,
                    "Dimensions": [
                        {"Name": name, "Value": str(val)}
                        for name, val in (dimensions or {}).items()
                    ],
                }],
            )
        except Exception as exc:
            # Metrics are observability, not control flow.
            print("visionguard: metrics publish failed: %s" % exc,
                  file=sys.stderr)

    def record_verdict(self, severity, latency_ms, tenant="default"):
        self.put("VerdictCount", 1,
                 dimensions={"Verdict": severity, "Tenant": tenant})
        self.put("InspectionLatencyMs", latency_ms, unit="Milliseconds",
                 dimensions={"Tenant": tenant})

    def record_denial(self, reason, tenant="default"):
        self.put("GatewayDenial", 1,
                 dimensions={"Reason": reason, "Tenant": tenant})
