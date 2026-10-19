"""Policy gateway: every inspection request passes through here.

The gateway enforces four things before any agent is allowed to act:
  1. API-key authentication: tenants with a configured key must present
     it; the key is checked before any metering happens.
  2. Rate limits (token bucket per tenant) so one line cannot flood the system.
  3. Confidence thresholds: low-confidence verdicts are held for human review
     instead of triggering quarantine or alerts.
  4. Action allow-lists: a tenant only gets the actions it is configured for.

It also meters every request (counts, denials, latencies) and appends a
JSON-lines audit log. Inspired by the API-gateway patterns used in
production LLM platforms: authenticate, meter, gate, then act.
"""
import hmac
import json
import os
import secrets
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Tuple


def generate_api_key(nbytes: int = 32) -> str:
    """Generate a fresh random API key. Store it server-side and hand the
    value to the tenant once; the gateway never logs key values."""
    return secrets.token_urlsafe(nbytes)


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
                 audit_path: str = "audit.log",
                 audit_sinks: List = None):
        """audit_sinks: callables receiving the full audit record dict.

        A sink failure never breaks an inspection: audit() catches sink
        exceptions and logs them to stderr.

        A tenant config may carry "api_key": a secret the tenant must
        present on every request. Tenants without one keep working
        unauthenticated, so auth is strictly opt-in per tenant.
        """
        self.tenants = tenants or {"default": dict(DEFAULT_TENANT)}
        self.audit_path = audit_path
        self.audit_sinks = list(audit_sinks or [])
        self._buckets: Dict[str, TokenBucket] = {}
        self._lock = threading.Lock()
        self._meters: Dict[str, dict] = {}

    @classmethod
    def from_env(cls, env: dict = None, **kwargs) -> "PolicyGateway":
        """Build a gateway with per-tenant API keys from the environment.

        VISIONGUARD_API_KEYS holds a JSON object mapping tenant names to
        their keys, e.g. '{"default": "sk-...", "acme": "sk-..."}'.
        Tenants named there but missing from `tenants` get the default
        config plus their key. Invalid JSON raises ValueError: a broken
        key config must fail loudly, not run unauthenticated.
        """
        env = env if env is not None else os.environ
        raw = env.get("VISIONGUARD_API_KEYS", "").strip()
        keys = {}
        if raw:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "VISIONGUARD_API_KEYS is not valid JSON: %s" % exc)
            if not isinstance(parsed, dict):
                raise ValueError(
                    "VISIONGUARD_API_KEYS must be a JSON object mapping "
                    "tenant names to keys")
            keys = {str(t): str(k) for t, k in parsed.items()}
        tenants = dict(kwargs.pop("tenants", None) or
                       {"default": dict(DEFAULT_TENANT)})
        for tenant, key in keys.items():
            cfg = tenants.get(tenant, dict(DEFAULT_TENANT))
            cfg = dict(cfg)
            cfg["api_key"] = key
            tenants[tenant] = cfg
        return cls(tenants=tenants, **kwargs)

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
        for sink in self.audit_sinks:
            try:
                sink(record)
            except Exception as exc:
                # Audit shipping is best effort; never fail an inspection.
                print("visionguard: audit sink failed: %s" % exc,
                      file=sys.stderr)

    def check_api_key(self, tenant: str,
                      api_key: str) -> Tuple[bool, str]:
        """Authenticate a tenant by its API key. Returns (allowed, reason).

        Tenants with no configured key are allowed through: auth is
        opt-in per tenant. The key value is compared in constant time and
        is never written to the audit log; rejections are audited as
        api_key_rejected with the tenant name only.
        """
        cfg = self._config(tenant)
        expected = cfg.get("api_key")
        if not expected:
            return True, "ok"
        if api_key and hmac.compare_digest(str(api_key), expected):
            return True, "ok"
        self.audit({"type": "api_key_rejected", "tenant": tenant,
                    "reason": "missing or invalid API key"})
        return False, "missing or invalid API key"

    def check_request(self, tenant: str = "default",
                      api_key: str = None) -> Tuple[bool, str]:
        """Gate an incoming inspection request. Returns (allowed, reason).

        The API key is checked first, before any metering, so rejected
        credentials never touch the request counters.
        """
        allowed, reason = self.check_api_key(tenant, api_key)
        if not allowed:
            return False, reason
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
