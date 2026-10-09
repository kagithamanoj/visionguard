# VisionGuard

Agentic visual inspection with guardrails. Three agents inspect a part,
reason about what they see, and act on it, while a policy gateway meters
every request and decides what the agents are allowed to do.

Built for the **OpenCV AI Competition 2026** (powered by AWS).

## How it works

1. **Detection agent** finds surface defects with classical computer vision
   (OpenCV 5): plate segmentation, dark-anomaly search, mounting-hole
   rejection, contrast-based scoring. Labels: scratch, dent, spot.
2. **Reasoning agent** turns detections into a severity verdict
   (none / minor / major / critical) with confidence and a rationale.
3. **Action agent** carries out the verdict: log, quarantine (file copy),
   alert (webhook stub).
4. **Policy gateway** gates everything: per-tenant rate limits, minimum
   confidence thresholds (low-confidence verdicts are held for human
   review), action allow-lists, request metering, and a JSON audit log.

```
image --> [gateway: rate limit] --> detect --> reason
                                       |
                              [gateway: confidence + allow-list]
                                       |
                          log / quarantine / alert / review
```

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1. Generate synthetic inspection images
python scripts/make_sample_images.py --count 20

# 2. Run the pipeline on one image
python -m visionguard.pipeline --image samples/defective_scratch_000.png

# 3. Run the API
uvicorn visionguard.api:app --port 8000
# POST /inspect  (multipart image upload -> verdict JSON)
# GET  /metrics  (per-tenant metering)
# GET  /health

# 4. Run the tests
python -m pytest tests/ -q

# 5. Generate the static results viewer
python scripts/make_results_viewer.py
# open viewer/index.html in a browser: gallery with detections, verdicts,
# and gateway metering, generated from a real pipeline run

# 6. Train the demo-scale CNN baseline (CPU, a few minutes)
python training/train_defect_detector.py --epochs 5 --samples 1000
```

## Project structure

```
visionguard/
  agents/
    detector.py      # OpenCV 5 defect detection
    reasoner.py      # rule-based severity verdicts (+ optional LLM judge hook)
    actor.py         # quarantine, alert, audit
  gateway/
    policy.py        # rate limiting, confidence gating, metering, audit log
  aws/
    lambda_handler.py  # S3-triggered inspection
    api_handler.py     # API Gateway adapter
  pipeline.py        # detect -> reason -> act orchestrator + CLI
  api.py             # FastAPI service
infra/
  terraform/         # S3, SQS, Lambda, DynamoDB, API Gateway (valid HCL)
  docker/Dockerfile  # Lambda container image
training/
  train_defect_detector.py  # small PyTorch CNN on synthetic patches
scripts/
  make_sample_images.py     # synthetic clean/defective plate images
  make_demo_video.py        # ffmpeg slideshow of pipeline verdicts
  make_results_viewer.py    # static HTML results viewer from a pipeline run
tests/               # pytest: detector, gateway, pipeline
docs/
  architecture.md    # components, data flow, AWS diagram
```

## AWS deployment

Terraform in `infra/terraform/` provisions S3 buckets (incoming,
quarantine, verdicts), an SQS dead-letter queue, two Lambda functions
(S3-triggered inspection and the API adapter) from one container image,
a DynamoDB audit table, and an HTTP API Gateway.

```bash
cd infra/terraform
terraform init
terraform apply -var="lambda_image_uri=<your-ecr-image-uri>"
```

Build and push the container image first (see `infra/docker/Dockerfile`).
Upload a `.png` to the incoming bucket and a verdict JSON lands in the
verdicts bucket; quarantined images land in the quarantine bucket.

## Notes

- The sample images and the CNN training set are synthetic. The CNN is a
  demo-scale baseline, not a production model; the classical detector is
  the primary path.
- The LLM judge hook is stubbed by design. The rule-based verdict stands
  on its own.
- Nothing here claims competition results. It was built for the event;
  results are whatever the judges decide.
