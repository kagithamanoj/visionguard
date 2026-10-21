import pytest

from visionguard.aws import metrics
from visionguard.aws.metrics import MetricsPublisher


class _FakeCloudWatch:
    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail

    def put_metric_data(self, Namespace, MetricData):
        if self.fail:
            raise RuntimeError("cloudwatch down")
        self.sent.append((Namespace, MetricData))


def test_from_env_off_by_default():
    pub = MetricsPublisher.from_env(env={})
    assert pub.enabled is False


def test_from_env_reads_flag():
    pub = MetricsPublisher.from_env(
        env={"VISIONGUARD_METRICS_ENABLED": "true"})
    assert pub.enabled is True
    pub = MetricsPublisher.from_env(
        env={"VISIONGUARD_METRICS_ENABLED": "yes"})
    assert pub.enabled is False


def test_disabled_publisher_never_touches_client():
    client = _FakeCloudWatch()
    pub = MetricsPublisher(enabled=False, client=client)
    pub.record_verdict("critical", 12.5, tenant="acme")
    pub.record_denial("rate limit exceeded", tenant="acme")
    assert client.sent == []


def test_record_verdict_publishes_count_and_latency():
    client = _FakeCloudWatch()
    pub = MetricsPublisher(enabled=True, client=client)
    pub.record_verdict("critical", 42.7, tenant="acme")
    assert len(client.sent) == 2

    ns, data = client.sent[0]
    assert ns == "VisionGuard/Inspection"
    assert len(data) == 1
    assert data[0]["MetricName"] == "VerdictCount"
    assert data[0]["Value"] == 1.0
    assert data[0]["Unit"] == "Count"
    dims = {d["Name"]: d["Value"] for d in data[0]["Dimensions"]}
    assert dims == {"Verdict": "critical", "Tenant": "acme"}

    ns, data = client.sent[1]
    assert ns == "VisionGuard/Inspection"
    assert data[0]["MetricName"] == "InspectionLatencyMs"
    assert data[0]["Value"] == pytest.approx(42.7)
    assert data[0]["Unit"] == "Milliseconds"


def test_record_denial_publishes_reason():
    client = _FakeCloudWatch()
    pub = MetricsPublisher(enabled=True, client=client)
    pub.record_denial("rate limit exceeded", tenant="acme")
    ns, data = client.sent[0]
    assert ns == "VisionGuard/Inspection"
    assert data[0]["MetricName"] == "GatewayDenial"
    dims = {d["Name"]: d["Value"] for d in data[0]["Dimensions"]}
    assert dims == {"Reason": "rate limit exceeded", "Tenant": "acme"}


def test_publish_failure_never_raises(capsys):
    client = _FakeCloudWatch(fail=True)
    pub = MetricsPublisher(enabled=True, client=client)
    # Metrics are observability, not control flow: this must not raise.
    pub.record_verdict("major", 3.0)
    pub.record_denial("tenant disabled")
    assert "metrics publish failed" in capsys.readouterr().err


def test_module_namespace_constant():
    assert metrics.NAMESPACE == "VisionGuard/Inspection"
    pub = MetricsPublisher(enabled=True, client=_FakeCloudWatch())
    pub.put("X", 1)
    ns, _ = pub._client.sent[0]
    assert ns == metrics.NAMESPACE
