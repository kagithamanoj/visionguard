# VisionGuard Roadmap

Backlog of improvements, ordered by judging value for the OpenCV AI
Competition 2026. Check items off as they land.

## High value

- [x] Demo video generator script (`scripts/make_demo_video.py`): ffmpeg slideshow of sample images with pipeline verdicts overlaid, one command to regenerate.
- [x] Static HTML results viewer (`viewer/`): gallery of sample images with detections, verdicts, and gateway metering, generated from a pipeline run. Built via `scripts/make_results_viewer.py`; regenerated 2026-10-09.
- [x] Detector tuning report: grid search over detector thresholds on the synthetic set, with precision/recall per defect type written to `docs/tuning_report.md`. Built via `scripts/tune_detector.py` (36 configs, 150 images, seed 20261012); current defaults confirmed optimal on this set, failure cliffs documented; generated 2026-10-12.
- [x] LLM judge via AWS Bedrock: `BedrockJudge` (`visionguard/agents/bedrock_judge.py`) calls Nova Lite through the Bedrock Converse API as an optional second opinion, gated by `VISIONGUARD_LLM_JUDGE_ENABLED` (off by default). Wired into pipeline CLI (`--llm-judge`), FastAPI service, and Lambda handler; Terraform adds `bedrock:InvokeModel` permission plus env vars. Invalid replies and AWS errors mean no second opinion, never faked. Landed 2026-10-14 with 12 new tests.
- [ ] DynamoDB audit wiring: ship the Lambda JSON-lines audit entries to the provisioned audit table instead of only the log stream.

## Medium value

- [ ] API key auth on the FastAPI service: per-tenant keys checked by the gateway before metering.
- [ ] CloudWatch dashboard and alarms: Terraform for a dashboard (invocations, verdict mix, gateway denials) plus an alarm on elevated critical rates.
- [ ] Load test: scripted run of the pipeline over N images capturing p50/p95 latency numbers into `docs/load_test.md`.

## Nice to have

- [ ] More defect types: add crack and corrosion to the sample generator and detector labels, with tests.
- [ ] CONTRIBUTING.md: how to run, test, and extend the project for anyone cloning the repo.
