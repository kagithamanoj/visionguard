# Devpost Submission Draft — VisionGuard
# OpenCV AI Competition 2026 (opencv26.devpost.com)
# STATUS: DRAFT — not submitted. Review before submitting.
# Submission deadline: Oct 27, 2026 @ 1:45am CDT

## Project name
VisionGuard

## Tagline
Agentic visual inspection with guardrails: OpenCV 5 defect detection, multi-agent reasoning, and a policy gateway that meters every decision.

## Built with
python, opencv, fastapi, aws-lambda, amazon-s3, amazon-sqs, amazon-dynamodb, terraform, pytorch, docker

## Links
- GitHub: https://github.com/kagithamanoj/visionguard
- Demo video: (to be produced — automated demo video planned)
- Try it out: clone the repo, run scripts/make_sample_images.py, then python -m visionguard.pipeline --image samples/defective_01.png

## Inspiration
I spend my working life building the guardrails around production AI systems: an enterprise LLM gateway with token metering, rate limiting, and audit logging. The pattern that kept repeating is that the model is rarely the failure point. The failure point is the ungoverned action around the model.

Vision systems have the same gap. A defect detector that cries wolf shuts down a line. One that misses a defect ships bad product. And a fully autonomous "see and act" loop with no policy layer is a liability no factory should accept. VisionGuard applies the gateway pattern to computer vision: agents that see, reason, and act, with every action passing through policy first.

## What it does
VisionGuard inspects images of manufactured parts and decides what to do about defects, end to end:

1. A detection agent finds candidate defects with OpenCV 5 classical computer vision: plate segmentation, dark-anomaly search, contour analysis with mounting-hole rejection (near-circular blobs with a bright machined ring are treated as fixtures, not defects), and contrast-based scoring that labels scratches, dents, and spots.
2. A reasoning agent turns detections into a severity verdict (none, minor, major, critical) with a confidence score and a written rationale. An LLM-judge hook exists for future vision-language review; the rule-based verdict stands alone today.
3. An action agent quarantines defective parts (copy, never delete), fires alerts, and writes audit entries.
4. A policy gateway governs every step: per-tenant token-bucket rate limits, minimum-confidence gating that holds low-confidence verdicts for human review, action allow-lists, request metering with average and p95 latency, and a JSON-lines audit log.

A FastAPI service exposes POST /inspect, GET /metrics, and GET /health. An AWS Lambda handler runs the same pipeline on S3 upload events, and Terraform provisions the full serverless stack: S3 buckets, SQS with dead-letter queue, Lambda functions, DynamoDB audit table, and an HTTP API Gateway.

## How we built it
The core pipeline is Python with OpenCV 5. The detector is classical CV, chosen deliberately: it runs on CPU in milliseconds, needs no GPU, and its decisions are explainable, which matters when a verdict quarantines a physical part. A small PyTorch CNN trainer is included as a demo-scale baseline on synthetic data, with the classical detector as the primary path.

Agent orchestration follows a strict detect, reason, act sequence with the policy gateway enforced between steps, so no agent can act outside its confidence threshold or rate budget. The cloud path mirrors the local path exactly: the Lambda handler calls the same pipeline code, and Terraform defines the S3, SQS, Lambda, DynamoDB, and API Gateway resources as code. CI runs the full 14-test suite on every push.

## Challenges we ran into
The hardest problem was false positives from mounting holes: near-circular machined features scored as defects under naive contour analysis. The fix was geometric reasoning in the detector itself, rejecting near-circular blobs with a bright machined ring before scoring. The second challenge was confidence calibration: a verdict the system is unsure about should not trigger the same action as a certain one, which is what led to the minimum-confidence gating and human-review hold in the policy gateway.

## Accomplishments that we're proud of
A working, tested, end-to-end agentic inspection system: 14 passing tests covering detection accuracy on synthetic samples, gateway rate-limiting and confidence gating, and full pipeline runs including quarantine and audit. The policy gateway is the piece we're proudest of: it brings metering, rate limiting, and human-in-the-loop control to vision agents, and it is the part most vision demos skip.

## What we learned
Classical computer vision is underrated for constrained inspection tasks: explainable, fast on CPU, and sufficient when the defect vocabulary is known. And the agentic lesson transferred directly from our LLM platform work: autonomy without policy is a demo, not a system. The guardrails are the product.

## What's next
Wire the LLM-judge hook to a vision-language model for ambiguous cases, connect the Lambda audit path to the provisioned DynamoDB table, deploy the Terraform stack to AWS, and evaluate the detector against a labeled real-world defect dataset.

## Judging notes (for our own targeting, not part of submission)
- Agentic Vision Award ($1,000): our primary target. OpenCV 5 + agent integration (detect/reason/act agents), orchestration with appropriate autonomy (gateway-enforced confidence gating + human review hold), task effectiveness (14 tests, evaluation on synthetic samples), failure handling and observability (quarantine, audit log, metering, p95 latency), docs and demo.
- Overall awards: technical execution (OpenCV 5 depth, architecture, reliability, evaluation), innovation (guardrailed vision agents), real-world impact (manufacturing QC), UX (CLI + REST API), documentation (README, architecture doc, video), cloud delivery (Terraform, Lambda, reproducibility).
