"""Policy gateway: every inspection request passes through here.

The gateway enforces three things before any agent is allowed to act:
  1. Rate limits (token bucket per tenant) so one line cannot flood the system.
  2. Confidence thresholds: low-confidence verdicts are held for human review
     instead of triggering quarantine or alerts.
  3. Action allow-lists: a tenant only gets the actions it is configured for.

It also meters every request (counts, denials, latencies) and appends a
JSON-lines audit log. Inspired by the API-gateway patterns used in
production LLM platforms: meter, gate, then act.
"""
import json
import os
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Tuple


class TokenBucket:
    def __init__(self, capacity: int, refill_per_second: float):
        self.capacity = float(capacity)
        self.refill_per_second = float(refill_per_second)
        self.tokens = float(capacity)
        self.updated = time.monotonic()
        self._lock = threading.Lock()

    def consume(self, amount: float = 1.0) -> bool:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self.updated
            self.tokens = min(self.capacity,
                              self.tokens + elapsed * self.refill_per_second)
            self.updated = now
            if self.tokens >= amount:
                self.tokens -= amount
                return True
            return False


class PolicyDenied(Exception):
    """Raised when the gateway refuses a request or an action."""


DEFAULT_TENANT = {
    "requests_per_minute": 60,
    "min_confidence": 0.60,
    "allowed_actions": ["log", "quarantine", "alert"],
    "enabled": True,
}


class PolicyGateway:
    def __init__(self,
                 tenants: Dict[str, dict] = None,
                 audit_path: str = "audit.log"):
        self.tenants = tenants or {"default": dict(DEFAULT_TENANT)}
        self.audit_path = audit_path
        self._buckets: Dict[str, TokenBucket] = {}
        self._lock = threading.Lock()
        self._meters: Dict[str, dict] = {}

    def _config(self, tenant: str) -> dict:
        return self.tenants.get(tenant, self.tenants.get("default",
                                                         DEFAULT_TENANT))

    def _bucket(self, tenant: str) -> TokenBucket:
        cfg = self._config(tenant)
        with self._lock:
            bucket = self._buckets.get(tenant)
            if bucket is None:
                rpm = cfg.get("requests_per_minute", 60)
                bucket = TokenBucket(capacity=rpm,
                                     refill_per_second=rpm / 60.0)
                self._buckets[tenant] = bucket
            return bucket

    def _meter(self, tenant: str) -> dict:
        with self._lock:
            m = self._meters.get(tenant)
            if m is None:
                m = {"requests": 0, "denied": 0, "latencies_ms": [],
                     "by_severity": {}}
                self._meters[tenant] = m
            return m

    def audit(self, entry: dict):
        record = {"at": datetime.now(timezone.utc).isoformat(), **entry}
        os.makedirs(os.path.dirname(os.path.abspath(self.audit_path)),
                    exist_ok=True)
        with open(self.audit_path, "a") as f:
            f.write(json.dumps(record) + "\n")

    def check_request(self, tenant: str = "default") -> Tuple[bool, str]:
        """Gate an incoming inspection request. Returns (allowed, reason)."""
        cfg = self._config(tenant)
        meter = self._meter(tenant)
        meter["requests"] += 1
        if not cfg.get("enabled", True):
            meter["denied"] += 1
            self.audit({"type": "request_denied", "tenant": tenant,
                        "reason": "tenant disabled"})
            return False, "tenant disabled"
        if not self._bucket(tenant).consume():
            meter["denied"] += 1
            self.audit({"type": "request_denied", "tenant": tenant,
                        "reason": "rate limit exceeded"})
            return False, "rate limit exceeded"
        self.audit({"type": "request_allowed", "tenant": tenant})
        return True, "ok"

    def check_verdict(self, tenant: str, verdict) -> Tuple[str, str]:
        """Gate the actions for a verdict.

        Returns (effective_severity, note). Low-confidence verdicts are
        downgraded to 'review' so nothing irreversible fires on a guess.
        """
        cfg = self._config(tenant)
        min_conf = cfg.get("min_confidence", 0.60)
        if verdict.severity != "none" and verdict.confidence < min_conf:
            self.audit({"type": "verdict_held", "tenant": tenant,
                        "severity": verdict.severity,
                        "confidence": verdict.confidence,
                        "min_confidence": min_conf})
            return "review", (f"confidence {verdict.confidence:.2f} below "
                              f"threshold {min_conf:.2f}; held for review")
        allowed = set(cfg.get("allowed_actions",
                              ["log", "quarantine", "alert"]))
        if verdict.severity == "critical" and "alert" not in allowed:
            self.audit({"type": "action_blocked", "tenant": tenant,
                        "action": "alert", "severity": "critical"})
            return "major", "alert not in tenant allow-list; downgraded"
        return verdict.severity, "ok"

    def record_result(self, tenant: str, severity: str,
                      latency_ms: float):
        meter = self._meter(tenant)
        meter["latencies_ms"].append(latency_ms)
        meter["by_severity"][severity] = \
            meter["by_severity"].get(severity, 0) + 1

    def get_metrics(self) -> dict:
        out = {}
        for tenant, m in self._meters.items():
            lat = m["latencies_ms"]
            out[tenant] = {
                "requests": m["requests"],
                "denied": m["denied"],
                "by_severity": dict(m["by_severity"]),
                "avg_latency_ms": round(sum(lat) / len(lat), 2) if lat else 0,
                "p95_latency_ms": round(sorted(lat)[int(len(lat) * 0.95)]
                                        if lat else 0, 2),
            }
        return out

    def audit_entries(self) -> List[dict]:
        if not os.path.exists(self.audit_path):
            return []
        entries = []
        with open(self.audit_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries
