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
  (scratch / dent / spot).

- **Reasoning agent** (`visionguard/agents/reasoner.py`)
  Deterministic rules turn detections into a severity verdict
  (none / minor / major / critical) with a confidence value and a
  human-readable rationale. An `LLMJudge` hook exists for an optional
  vision-language second opinion; it is stubbed and never faked.

- **Action agent** (`visionguard/agents/actor.py`)
  Carries out the verdict: `log` always, `quarantine` (file copy, never a
  move or delete) for major and up, `alert` (stdout plus optional webhook)
  for critical. Every action is reported back for the audit trail.

- **Policy gateway** (`visionguard/gateway/policy.py`)
  The bouncer. Per-tenant token-bucket rate limits, minimum-confidence
  thresholds (low-confidence verdicts are held for human review instead of
  firing actions), and action allow-lists (a tenant without `alert` cannot
  trigger alerts; critical is downgraded to major). It meters requests,
  denials, per-severity counts, and latencies, and appends a JSON-lines
  audit log.

- **Pipeline** (`visionguard/pipeline.py`)
  Orchestrator: `check_request` -> detect -> reason -> `check_verdict` ->
  act -> meter. Nothing acts without passing the gate.

- **FastAPI service** (`visionguard/api.py`)
  `POST /inspect` (image upload -> verdict JSON), `GET /metrics`,
  `GET /health`.

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
Terraform overrides the CMD per function. The DynamoDB table is provisioned
for a future step that ships the local JSON-lines audit log to DynamoDB;
today the Lambda writes audit entries to its own log stream and the local
service writes `audit.log`.

## Local vs AWS

Local development and CI run the pipeline in-process (`python -m
visionguard.pipeline --image ...`) or behind FastAPI. AWS runs the same
code in Lambda; the agents and gateway are deployment-agnostic. The
training script (`training/train_defect_detector.py`) is independent of
both: it produces a small CNN baseline on synthetic patches.

## What is stubbed, honestly

- `LLMJudge.judge()` returns `None` by default. Wire a real vision model
  endpoint here if you want a second opinion; the rule-based verdict
  stands on its own either way.
- The actor webhook only fires if `webhook_url` is configured; otherwise
  alerts are log lines.
- The CNN in `training/` is a demo-scale baseline on synthetic data, not a
  production defect model. The classical detector is the primary path.
