# VisionGuard Architecture

VisionGuard is an agentic visual-inspection system with a policy gateway.
Three agents do the work; a gateway decides whether they are allowed to.

## Components

- **Detection agent** (`visionguard/agents/detector.py`)
  Classical computer vision on OpenCV: grayscale, Gaussian blur, plate
  segmentation, dark-anomaly search inside the plate, mounting-hole
  rejection (near-circular blobs with a bright machined ring are fixtures,
  not defects), then per-defect scoring from contrast. Output: a list of
  detections with bounding box, area, score 0-1, and label
  (scratch / dent / spot / crack / corrosion). Cracks are thin branching
  lines that fill little of their bounding rectangle; corrosion is
  reddish in colour, unlike the gray defects.

- **Reasoning agent** (`visionguard/agents/reasoner.py`)
  Deterministic rules turn detections into a severity verdict
  (none / minor / major / critical) with a confidence value and a
  human-readable rationale. An optional `BedrockJudge`
  (`visionguard/agents/bedrock_judge.py`) adds a vision-language
  second opinion through the Bedrock Converse API when
  `VISIONGUARD_LLM_JUDGE_ENABLED=true`; it never changes the verdict,
  it only records whether it agreed or disagreed. Off by default.

- **Action agent** (`visionguard/agents/actor.py`)
  Carries out the verdict: `log` always, `quarantine` (file copy, never a
  move or delete) for major and up, `alert` (stdout plus optional webhook)
  for critical. Every action is reported back for the audit trail.

- **Policy gateway** (`visionguard/gateway/policy.py`)
  The bouncer. Per-tenant API-key authentication (checked before any
  metering; constant-time compare; rejections audited without logging the
  key), per-tenant token-bucket rate limits, minimum-confidence
  thresholds (low-confidence verdicts are held for human review instead of
  firing actions), and action allow-lists (a tenant without `alert` cannot
  trigger alerts; critical is downgraded to major). It meters requests,
  denials, per-severity counts, and latencies, and appends a JSON-lines
  audit log. Keys come from tenant config or the `VISIONGUARD_API_KEYS`
  env var; tenants without a key stay unauthenticated.

- **Pipeline** (`visionguard/pipeline.py`)
  Orchestrator: `check_request` -> detect -> reason -> `check_verdict` ->
  act -> meter. Nothing acts without passing the gate.

- **FastAPI service** (`visionguard/api.py`)
  `POST /inspect` (image upload -> verdict JSON), `GET /metrics`,
  `GET /health`. `/inspect` and `/metrics` require the `X-API-Key` header
  when the tenant has a key configured (401 otherwise); `/metrics` returns
  only the authenticated tenant's metering; `/health` stays open.

## Data flow

```
image --> [gateway: rate limit] --> detector --> reasoner
                                              |
                                     [gateway: confidence + allow-list]
                                              |
                        +----------+----------+----------+
                        |          |          |          |
                       log    quarantine    alert     review
                        (audit log records every step)
```

## AWS deployment

```
                      +-------------------------+
                      |  S3 incoming bucket     |
                      +------------+------------+
                                   | ObjectCreated (*.png)
                                   v
                      +-------------------------+
                      |  Lambda: inspect        |  container image
                      |  (lambda_handler)       |  (OpenCV + torch +
                      +-----+------------+------+   visionguard)
                            |            |
                verdict JSON |            | quarantine copy
                            v            v
               +----------------+  +------------------+
               | S3 verdicts    |  | S3 quarantine    |
               | bucket         |  | bucket           |
               +----------------+  +------------------+

  HTTP API Gateway --> Lambda: api (api_handler)
      POST /inspect   GET /metrics   GET /health

  Supporting: SQS dead-letter queue for failed invocations,
  DynamoDB audit table (tenant, timestamp) with TTL.
```

Terraform for all of the above lives in `infra/terraform/`. The Lambda
functions run from one container image (`infra/docker/Dockerfile`);
Terraform overrides the CMD per function. The DynamoDB audit table ships
the Lambda JSON-lines audit entries (see `visionguard/aws/dynamodb_audit.py`),
and the local service writes `audit.log`.

## Monitoring

The inspect Lambda publishes best-effort custom metrics into the
`VisionGuard/Inspection` CloudWatch namespace (`visionguard/aws/metrics.py`,
gated by `VISIONGUARD_METRICS_ENABLED`, on in the Terraform stack): one
`VerdictCount` datum per finished inspection (dimensioned by verdict and
tenant), one `GatewayDenial` datum per gateway refusal (dimensioned by
reason and tenant), and the inspection latency. `infra/terraform/cloudwatch.tf`
provisions a dashboard (invocations, verdict mix, gateway denials, errors,
latency, throttles), an SNS alert topic, and two alarms: one on an elevated
critical-verdict rate and one on a gateway-denial spike. Thresholds and the
optional alarm email address are variables (`critical_verdicts_per_5min`,
`gateway_denials_per_5min`, `alarm_notification_email`).

## Local vs AWS

Local development and CI run the pipeline in-process (`python -m
visionguard.pipeline --image ...`) or behind FastAPI. AWS runs the same
code in Lambda; the agents and gateway are deployment-agnostic. The
training script (`training/train_defect_detector.py`) is independent of
both: it produces a small CNN baseline on synthetic patches.

## What is stubbed, honestly

- The base `LLMJudge.judge()` returns `None` by default. The real
  second opinion is `BedrockJudge`, wired to Bedrock Nova Lite and
  gated by `VISIONGUARD_LLM_JUDGE_ENABLED`; the rule-based verdict
  stands on its own either way, and any invalid reply or AWS error is
  treated as no second opinion, never faked.
- The actor webhook only fires if `webhook_url` is configured; otherwise
  alerts are log lines.
- The CNN in `training/` is a demo-scale baseline on synthetic data, not a
  production defect model. The classical detector is the primary path.
