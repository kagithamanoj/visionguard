"""Ships gateway audit entries to the provisioned DynamoDB audit table.

The table is defined in infra/terraform/dynamodb.tf: partition key
`tenant`, sort key `at`, TTL attribute `expires_at`. One row per audit
entry. The sort key is the entry timestamp plus a random suffix so two
entries stamped in the same microsecond never clobber each other.

Usage in the Lambda handler:

    gateway = PolicyGateway(audit_path="/tmp/audit.log")
    shipper = DynamoDBAudit.from_env()      # reads AUDIT_TABLE
    if shipper.enabled:
        gateway.audit_sinks.append(shipper)

Shipping is best effort: a sink failure never breaks an inspection. The
gateway catches sink exceptions and logs them to stderr.
"""
import math
import os
import time
import uuid
from datetime import datetime, timezone

import boto3

TTL_DAYS = 90


def _to_attr(value):
    """Convert a plain Python value to a DynamoDB attribute-value dict."""
    if value is None:
        return {"NULL": True}
    if isinstance(value, bool):
        return {"BOOL": value}
    if isinstance(value, int):
        return {"N": str(value)}
    if isinstance(value, float):
        if math.isfinite(value):
            return {"N": repr(value)}
        # DynamoDB numbers reject NaN and Infinity; store as strings.
        return {"S": repr(value)}
    if isinstance(value, str):
        return {"S": value}
    if isinstance(value, (list, tuple)):
        return {"L": [_to_attr(item) for item in value]}
    if isinstance(value, dict):
        return {"M": {str(k): _to_attr(v) for k, v in value.items()}}
    return {"S": str(value)}


class DynamoDBAudit:
    """A gateway audit sink that writes one row per entry to DynamoDB."""

    def __init__(self, table_name, ttl_days=TTL_DAYS, client=None,
                 time_fn=None):
        self.table_name = table_name
        self.ttl_days = ttl_days
        self._client = client
        self._time = time_fn or time.time

    @classmethod
    def from_env(cls, env_var="AUDIT_TABLE"):
        return cls(table_name=os.environ.get(env_var, ""))

    @property
    def enabled(self):
        return bool(self.table_name)

    def _dynamodb(self):
        if self._client is None:
            self._client = boto3.client("dynamodb")
        return self._client

    def __call__(self, record):
        if not self.enabled:
            return
        at = record.get("at") or datetime.now(timezone.utc).isoformat()
        item = {
            "tenant": {"S": str(record.get("tenant", "default"))},
            "at": {"S": "%s#%s" % (at, uuid.uuid4().hex[:12])},
            "expires_at": {"N": str(int(self._time()) +
                                    self.ttl_days * 86400)},
        }
        for key, value in record.items():
            if key in ("tenant", "at"):
                continue
            item[key] = _to_attr(value)
        self._dynamodb().put_item(TableName=self.table_name, Item=item)
