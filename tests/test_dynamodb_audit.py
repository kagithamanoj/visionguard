from visionguard.aws.dynamodb_audit import DynamoDBAudit, _to_attr
from visionguard.gateway.policy import PolicyGateway


class _FakeDynamo:
    def __init__(self):
        self.puts = []

    def put_item(self, TableName, Item):
        self.puts.append((TableName, Item))


def _record():
    return {"type": "request_allowed", "tenant": "acme",
            "at": "2026-10-16T12:00:00.123456+00:00"}


def test_to_attr_conversions():
    assert _to_attr("hi") == {"S": "hi"}
    assert _to_attr(3) == {"N": "3"}
    assert _to_attr(0.5) == {"N": "0.5"}
    assert _to_attr(True) == {"BOOL": True}
    assert _to_attr(None) == {"NULL": True}
    assert _to_attr(["a", 1]) == {"L": [{"S": "a"}, {"N": "1"}]}
    assert _to_attr({"k": "v"}) == {"M": {"k": {"S": "v"}}}
    # Non-finite floats cannot be DynamoDB numbers.
    assert _to_attr(float("nan")) == {"S": "nan"}
    assert _to_attr(float("inf")) == {"S": "inf"}


def test_ship_writes_expected_item():
    client = _FakeDynamo()
    ship = DynamoDBAudit("audit-table", ttl_days=90, client=client,
                         time_fn=lambda: 1_000_000.0)
    ship(_record())
    assert len(client.puts) == 1
    table, item = client.puts[0]
    assert table == "audit-table"
    assert item["tenant"] == {"S": "acme"}
    assert item["at"]["S"].startswith("2026-10-16T12:00:00.123456+00:00#")
    assert item["type"] == {"S": "request_allowed"}
    assert item["expires_at"] == {"N": str(1_000_000 + 90 * 86400)}


def test_sort_keys_are_unique_per_entry():
    client = _FakeDynamo()
    ship = DynamoDBAudit("audit-table", client=client)
    ship(_record())
    ship(_record())
    keys = [item["at"]["S"] for _, item in client.puts]
    assert keys[0] != keys[1]


def test_missing_tenant_defaults():
    client = _FakeDynamo()
    ship = DynamoDBAudit("audit-table", client=client)
    ship({"type": "request_allowed", "at": "t0"})
    _, item = client.puts[0]
    assert item["tenant"] == {"S": "default"}


def test_disabled_without_table_name():
    client = _FakeDynamo()
    ship = DynamoDBAudit("", client=client)
    assert ship.enabled is False
    ship(_record())
    assert client.puts == []


def test_gateway_fans_audit_out_to_sinks(tmp_path):
    seen = []
    gw = PolicyGateway(tenants={"t": {"requests_per_minute": 60,
                                      "min_confidence": 0.6,
                                      "allowed_actions": ["log"],
                                      "enabled": True}},
                       audit_path=str(tmp_path / "audit.log"),
                       audit_sinks=[seen.append])
    gw.check_request("t")
    assert len(seen) == 1
    assert seen[0]["type"] == "request_allowed"
    assert seen[0]["tenant"] == "t"
    assert "at" in seen[0]
    # The JSON-lines file still gets the same record.
    assert len(gw.audit_entries()) == 1
    assert gw.audit_entries()[0]["type"] == "request_allowed"


def test_failing_sink_does_not_break_gateway(tmp_path, capsys):
    def boom(record):
        raise RuntimeError("dynamo down")

    seen = []
    gw = PolicyGateway(tenants={"t": {"requests_per_minute": 60,
                                      "min_confidence": 0.6,
                                      "allowed_actions": ["log"],
                                      "enabled": True}},
                       audit_path=str(tmp_path / "audit.log"),
                       audit_sinks=[boom, seen.append])
    allowed, _ = gw.check_request("t")
    assert allowed is True
    assert len(seen) == 1  # later sinks still fire
    assert len(gw.audit_entries()) == 1  # file still written
    assert "audit sink failed" in capsys.readouterr().err
