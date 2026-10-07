# VisionGuard Demo Video Script
# Target length: 2 minutes 45 seconds. Read at a natural pace, about 140 words per minute.
# Recording: Loom, OBS, or phone on tripod. 1080p, quiet room, terminal font size 16+.
# Upload: YouTube as UNLISTED. Paste the link into the Devpost submission form.

---

## 0:00 - 0:20 | HOOK AND PROBLEM
[SCREEN: title card or the GitHub repo README]

"Factory cameras catch thousands of parts a day, but the software watching them has a trust problem. A detector that cries wolf shuts down the line. One that misses a defect ships bad product. And a fully autonomous vision system with no policy layer is something no factory should deploy.

VisionGuard fixes that. It is an agentic visual inspection system where agents see, reason, and act, and every action passes through a policy gateway first."

## 0:20 - 1:20 | LIVE DEMO
[SCREEN: terminal, large font]

"Let me show it running. First I generate a test image, then I run the full pipeline on it."

[Run, reading the commands aloud as you type:]
python scripts/make_sample_images.py
python -m visionguard.pipeline --image samples/defective_01.png

[Point at the output as it appears:]
"The detection agent found two candidate defects and scored them. The reasoning agent returned a major severity verdict with 87 percent confidence and a written rationale. The action agent quarantined the image and wrote an audit entry. The whole run took under a second on CPU."

[SCREEN: switch to browser, FastAPI docs at localhost:8000/docs]

"The same pipeline is exposed as a REST API. I POST an image to /inspect and get the verdict back as JSON, and /metrics shows the gateway metering: request counts and latency percentiles."

[Run:]
uvicorn visionguard.api:app --reload
[Then demo the POST in the docs UI or with curl.]

## 1:20 - 2:10 | ARCHITECTURE
[SCREEN: docs/architecture.md or a simple diagram]

"Four pieces. The detection agent uses OpenCV 5 classical computer vision: plate segmentation, contour analysis, and geometric rejection of mounting holes so machined features are not scored as defects. The reasoning agent turns detections into severity verdicts with confidence scores. The action agent quarantines and alerts.

Between them sits the policy gateway, the part I am proudest of. Per-tenant rate limits, minimum confidence thresholds that hold uncertain verdicts for human review, action allow-lists, and a full audit log. No agent acts outside policy. That is the piece most vision demos skip, and it is what makes this deployable."

## 2:10 - 2:45 | RESULTS AND CLOSE
[SCREEN: terminal running pytest, or the test summary]

"Fourteen tests, all passing: detection accuracy on synthetic samples, gateway rate limiting and confidence gating, and end-to-end pipeline runs including quarantine and audit. The classical detector was a deliberate choice: it runs in milliseconds on CPU and its decisions are explainable, which matters when a verdict quarantines a physical part.

Next steps are wiring a vision-language judge for ambiguous cases, connecting the audit path to DynamoDB, and deploying the Terraform stack to AWS.

VisionGuard: agents that see, reason, and act, with guardrails on every decision. Code is linked below. Thanks for watching."

[SCREEN: end card with repo URL: github.com/kagithamanoj/visionguard]

---

## Recording checklist
- [ ] One practice run reading the script aloud with a timer. Aim for 2:30 to 3:00.
- [ ] Terminal font 16pt or larger, dark background, clear contrast.
- [ ] Close notifications and unrelated tabs before recording.
- [ ] Generate fresh sample images right before recording so the demo is live, not staged.
- [ ] Speak the commands as you type them; pause a beat on the verdict JSON so viewers can read it.
- [ ] If you stumble, pause 3 seconds and restart the sentence. Edit out the pause later, or leave it. Judges prefer real over polished.
- [ ] Export 1080p, upload to YouTube as UNLISTED, copy the link into the Devpost submission.
