# VisionGuard Roadmap

Backlog of improvements, ordered by judging value for the OpenCV AI
Competition 2026. Check items off as they land.

## High value

- [x] Demo video generator script (`scripts/make_demo_video.py`): ffmpeg slideshow of sample images with pipeline verdicts overlaid, one command to regenerate.
- [x] Static HTML results viewer (`viewer/`): gallery of sample images with detections, verdicts, and gateway metering, generated from a pipeline run. Built via `scripts/make_results_viewer.py`; regenerated 2026-10-09.
- [x] Detector tuning report: grid search over detector thresholds on the synthetic set, with precision/recall per defect type written to `docs/tuning_report.md`. Built via `scripts/tune_detector.py` (36 configs, 150 images, seed 20261012); current defaults confirmed optimal on this set, failure cliffs documented; generated 2026-10-12.
- [x] LLM judge via AWS Bedrock: `BedrockJudge` (`visionguard/agents/bedrock_judge.py`) calls Nova Lite through the Bedrock Converse API as an optional second opinion, gated by `VISIONGUARD_LLM_JUDGE_ENABLED` (off by default). Wired into pipeline CLI (`--llm-judge`), FastAPI service, and Lambda handler; Terraform adds `bedrock:InvokeModel` permission plus env vars. Invalid replies and AWS errors mean no second opinion, never faked. Landed 2026-10-14 with 12 new tests.
- [x] DynamoDB audit wiring: ship the Lambda JSON-lines audit entries to the provisioned audit table instead of only the log stream. `DynamoDBAudit` (`visionguard/aws/dynamodb_audit.py`) is a gateway audit sink writing one row per entry (tenant/at keys, random suffix on the sort key, 90-day TTL) via `AUDIT_TABLE`; wired into the Lambda handler and Terraform env vars; sink failures are best-effort and never break an inspection. Landed 2026-10-16 with 7 new tests.

## Medium value

- [x] API key auth on the FastAPI service: per-tenant keys checked by the gateway before metering. Tenant configs accept `api_key`, also loadable from the `VISIONGUARD_API_KEYS` JSON env var via `PolicyGateway.from_env()`; `check_api_key` runs before metering in `check_request` with a constant-time compare, and rejections are audited without logging the key value. `/inspect` and `/metrics` require the `X-API-Key` header (401 on missing/wrong key), `/health` stays open, `/metrics` is scoped to the authenticated tenant, and the pipeline CLI gained `--api-key`. Keys are minted with `scripts/new_api_key.py`. Landed 2026-10-19 with 16 new tests.
- [x] CloudWatch dashboard and alarms: Terraform for a dashboard (invocations, verdict mix, gateway denials) plus an alarm on elevated critical rates. `MetricsPublisher` (`visionguard/aws/metrics.py`) publishes best-effort custom metrics into the `VisionGuard/Inspection` namespace (VerdictCount, GatewayDenial, InspectionLatencyMs), gated by `VISIONGUARD_METRICS_ENABLED`; wired into the inspect Lambda (denials on PolicyDenied, verdict plus latency per finished inspection), never breaking an inspection. `infra/terraform/cloudwatch.tf` provisions the dashboard (6 widgets: invocations, verdict mix, gateway denials, errors, latency, throttles), an SNS alert topic with optional email subscription, and two alarms: elevated critical-verdict rate and gateway-denial spike (thresholds as variables). IAM grants `cloudwatch:PutMetricData` scoped to the namespace; monitoring documented in `docs/architecture.md`. Landed 2026-10-21 with 7 new tests.
- [ ] Load test: scripted run of the pipeline over N images capturing p50/p95 latency numbers into `docs/load_test.md`.

## Nice to have

- [ ] More defect types: add crack and corrosion to the sample generator and detector labels, with tests.
- [ ] CONTRIBUTING.md: how to run, test, and extend the project for anyone cloning the repo.
