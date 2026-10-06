# VisionGuard Roadmap

Backlog of improvements, ordered by judging value for the OpenCV AI
Competition 2026. Check items off as they land.

## High value

- [ ] Demo video generator script (`scripts/make_demo_video.py`): ffmpeg slideshow of sample images with pipeline verdicts overlaid, one command to regenerate.
- [ ] Static HTML results viewer (`viewer/`): gallery of sample images with detections, verdicts, and gateway metering, generated from a pipeline run.
- [ ] Detector tuning report: grid search over detector thresholds on the synthetic set, with precision/recall per defect type written to `docs/tuning_report.md`.
- [ ] LLM judge via AWS Bedrock: wire the stubbed `LLMJudge` hook to a real vision model as an optional second opinion, gated by config.
- [ ] DynamoDB audit wiring: ship the Lambda JSON-lines audit entries to the provisioned audit table instead of only the log stream.

## Medium value

- [ ] API key auth on the FastAPI service: per-tenant keys checked by the gateway before metering.
- [ ] CloudWatch dashboard and alarms: Terraform for a dashboard (invocations, verdict mix, gateway denials) plus an alarm on elevated critical rates.
- [ ] Load test: scripted run of the pipeline over N images capturing p50/p95 latency numbers into `docs/load_test.md`.

## Nice to have

- [ ] More defect types: add crack and corrosion to the sample generator and detector labels, with tests.
- [ ] CONTRIBUTING.md: how to run, test, and extend the project for anyone cloning the repo.
