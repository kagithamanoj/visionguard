"""Generate the VisionGuard demo video.

Renders a slideshow of sample inspection images: the detection agent's
bounding boxes drawn on each image with the reasoning agent's verdict,
confidence, latency, and the actions taken, overlaid as banners. A title
card opens the video and a results card closes it.

Everything shown comes from real pipeline runs: the script executes
run_pipeline() on every sample image, so the verdicts and numbers in the
video match the current code. Regenerate with one command:

    python scripts/make_demo_video.py [--out demo.mp4] [--seconds-per-image N]

Requires ffmpeg on PATH (libx264) and the visionguard venv active.
"""
import argparse
import csv
import os
import subprocess
import sys
import tempfile
import textwrap

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from visionguard.agents.actor import ActorAgent  # noqa: E402
from visionguard.agents.detector import DetectorAgent  # noqa: E402
from visionguard.agents.reasoner import ReasonerAgent  # noqa: E402
from visionguard.gateway.policy import PolicyGateway  # noqa: E402
from visionguard.pipeline import run_pipeline  # noqa: E402

FPS = 30
IMG_W, IMG_H = 960, 720          # sample image render size
TOP_BAR_H = 70
BANNER_H = 170
FRAME_W = IMG_W
FRAME_H = IMG_H + TOP_BAR_H + BANNER_H

FONT = cv2.FONT_HERSHEY_SIMPLEX
SEVERITY_COLOR = {               # BGR
    "none": (46, 160, 67),
    "minor": (0, 200, 255),
    "major": (0, 127, 255),
    "critical": (50, 50, 220),
}
DARK = (24, 24, 24)
LIGHT = (240, 240, 240)
MID = (180, 180, 180)


def _draw_bar(frame, y0, h, color):
    frame[y0:y0 + h, :] = color


def _text(frame, text, pos, scale=0.7, color=LIGHT, thickness=2):
    cv2.putText(frame, text, pos, FONT, scale, color, thickness,
                cv2.LINE_AA)


def _wrap(frame, text, x, y, max_w, scale=0.55, color=MID, thickness=1):
    # Hershey fonts have no kerning table here; estimate chars per line
    # from an average glyph width at this scale.
    char_w = int(11 * scale / 0.55)
    for line in textwrap.wrap(text, width=max(max_w // char_w, 20))[:3]:
        _text(frame, line, (x, y), scale, color, thickness)
        y += int(24 * scale / 0.55)


def render_card(lines, footer=None):
    """Full-frame dark card with centered lines; lines are
    (text, scale, color) tuples."""
    frame = np.full((FRAME_H, FRAME_W, 3), DARK, dtype=np.uint8)
    y = FRAME_H // 2 - (len(lines) - 1) * 40
    for text, scale, color in lines:
        (w, _), _ = cv2.getTextSize(text, FONT, scale, 2)
        _text(frame, text, ((FRAME_W - w) // 2, y), scale, color, 2)
        y += 80
    if footer:
        _text(frame, footer, (30, FRAME_H - 30), 0.6, MID, 1)
    return frame


def render_slide(img_path, result):
    """One slide: annotated image with detection boxes and a verdict banner."""
    img = cv2.imread(img_path)
    if img is None:
        raise FileNotFoundError(f"cannot read image: {img_path}")
    img = cv2.resize(img, (IMG_W, IMG_H))
    detections = result["detections"]
    verdict = result["verdict"]
    actions = result["actions"]

    for d in detections:
        x, y, w, h = [int(v) for v in d["bbox"]]
        sx, sy = IMG_W / 640, IMG_H / 480
        x1, y1, x2, y2 = int(x * sx), int(y * sy), int((x + w) * sx), \
            int((y + h) * sy)
        color = SEVERITY_COLOR.get(verdict["severity"], LIGHT)
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 3)
        tag = f"{d['label']} {d['defect_score']:.2f}"
        (tw, th), _ = cv2.getTextSize(tag, FONT, 0.55, 1)
        ty = max(y1 - 8, th + 6)
        cv2.rectangle(img, (x1, ty - th - 8), (x1 + tw + 8, ty + 4),
                      color, -1)
        _text(img, tag, (x1 + 4, ty - 4), 0.55, (255, 255, 255), 1)

    frame = np.zeros((FRAME_H, FRAME_W, 3), dtype=np.uint8)
    _draw_bar(frame, 0, TOP_BAR_H, DARK)
    _text(frame, "VisionGuard inspection", (24, 45), 0.85, LIGHT, 2)
    _text(frame, os.path.basename(img_path), (FRAME_W - 420, 45), 0.7,
          MID, 1)
    frame[TOP_BAR_H:TOP_BAR_H + IMG_H, :] = img

    by = TOP_BAR_H + IMG_H
    sev = verdict["severity"]
    color = SEVERITY_COLOR.get(sev, LIGHT)
    _draw_bar(frame, by, BANNER_H, DARK)
    cv2.rectangle(frame, (24, by + 18), (200, by + 74), color, -1)
    _text(frame, sev.upper(), (40, by + 58), 0.85, (255, 255, 255), 2)
    _text(frame,
          f"confidence {verdict['confidence']:.2f}   "
          f"latency {result['latency_ms']:.0f} ms   "
          f"detections {len(detections)}",
          (224, by + 58), 0.7, LIGHT, 1)
    _text(frame, "actions: " + (", ".join(actions.get("actions", []))
                                or "none"),
          (24, by + 104), 0.6, MID, 1)
    _wrap(frame, "reason: " + verdict["rationale"], 24, by + 132, FRAME_W - 48)
    return frame


def collect_results(samples_dir):
    """Run the real pipeline on every labeled sample image.

    Quarantine copies and audit entries go to a temp dir so the demo run
    does not touch the repo's working files.
    """
    labels = {}
    labels_path = os.path.join(samples_dir, "labels.csv")
    if os.path.exists(labels_path):
        with open(labels_path) as f:
            for row in csv.DictReader(f):
                labels[row["filename"]] = row["label"]

    names = sorted(n for n in os.listdir(samples_dir)
                   if n.lower().endswith(".png"))
    # defective plates first so the video tells a story
    names.sort(key=lambda n: 0 if n.startswith("defective") else 1)

    tmp = tempfile.mkdtemp(prefix="visionguard_demo_")
    gateway = PolicyGateway(
        tenants={"demo": {"requests_per_minute": 6000,
                          "min_confidence": 0.60,
                          "allowed_actions": ["log", "quarantine", "alert"],
                          "enabled": True}},
        audit_path=os.path.join(tmp, "audit.log"))
    detector, reasoner = DetectorAgent(), ReasonerAgent()
    actor = ActorAgent(quarantine_dir=os.path.join(tmp, "quarantine"),
                       audit=gateway.audit)

    results = []
    for name in names:
        path = os.path.join(samples_dir, name)
        result = run_pipeline(path, tenant="demo", detector=detector,
                              reasoner=reasoner, actor=actor,
                              gateway=gateway)
        result["label"] = labels.get(name, "unknown")
        results.append((path, result))
        print(f"{name}: verdict={result['verdict']['severity']} "
              f"conf={result['verdict']['confidence']:.2f} "
              f"latency={result['latency_ms']:.0f}ms")
    return results


def write_video(frames, out_path, seconds_title=3, seconds_end=4,
                seconds_per_image=3):
    """Pipe raw BGR frames to ffmpeg (libx264)."""
    cmd = ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
           "-s", f"{FRAME_W}x{FRAME_H}", "-framerate", str(FPS),
           "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-crf", "20", "-preset", "medium", out_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    for frame in frames:
        proc.stdin.write(frame.tobytes())
    proc.stdin.close()
    rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg exited with code {rc}")
    return out_path


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--images", default="samples",
                   help="directory of sample images (default: samples)")
    p.add_argument("--out", default="visionguard-demo.mp4",
                   help="output video path")
    p.add_argument("--seconds-per-image", type=float, default=3.0)
    p.add_argument("--seconds-title", type=float, default=3.0)
    p.add_argument("--seconds-end", type=float, default=4.0)
    a = p.parse_args()

    collected = collect_results(a.images)
    if not collected:
        raise SystemExit(f"no PNG images found in {a.images}")

    per_img = int(FPS * a.seconds_per_image)
    frames = []
    frames += [render_card([
        ("VisionGuard", 1.6, LIGHT),
        ("Agentic visual inspection with guardrails", 0.9, MID),
        ("OpenCV AI Competition 2026", 0.8, SEVERITY_COLOR["minor"]),
    ])] * int(FPS * a.seconds_title)

    counts = {}
    latencies = []
    for img_path, result in collected:
        sev = result["verdict"]["severity"]
        counts[sev] = counts.get(sev, 0) + 1
        latencies.append(result["latency_ms"])
        frames += [render_slide(img_path, result)] * per_img

    mean_ms = sum(latencies) / len(latencies)
    order = ["none", "minor", "major", "critical", "review"]
    mix = ", ".join(f"{s}: {counts.get(s, 0)}"
                    for s in order if s in counts)
    frames += [render_card([
        ("Results", 1.4, LIGHT),
        (f"{len(collected)} images inspected", 0.9, LIGHT),
        (f"verdicts: {mix}", 0.8, MID),
        (f"mean pipeline latency: {mean_ms:.0f} ms on CPU", 0.8, MID),
    ], footer="github.com/kagithamanoj/visionguard")] * int(FPS * a.seconds_end)

    out = write_video(frames, a.out)
    print(f"wrote {out} ({len(frames) / FPS:.1f}s, "
          f"{len(collected)} slides, mean latency {mean_ms:.0f} ms)")


if __name__ == "__main__":
    main()
