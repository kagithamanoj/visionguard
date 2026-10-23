"""Scripted load test: run the full inspection pipeline over N images.

Generates a fixed-seed synthetic dataset (640x480 plates, half clean and
half defective), warms up once, then runs run_pipeline end to end on each
image and records the latency_ms the pipeline reports. Results (p50/p95
plus supporting stats) are written to docs/load_test.md.

The gateway rate limiter is not the thing under test, so the load-test
tenant is configured with a very high request budget: tokens are still
consumed per request (the limiter path executes), but no request is
denied, so the measured numbers reflect pipeline speed, not throttling.
The LLM judge stays off, matching the default pipeline.

Run: python scripts/load_test.py [--images N] [--image-dir DIR]
                                 [--seed S] [--out REPORT]
"""
import argparse
import os
import platform
import sys
import tempfile
from datetime import date

import cv2
import numpy as np
import torch

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from make_sample_images import generate

from visionguard.agents.actor import ActorAgent
from visionguard.agents.detector import DetectorAgent
from visionguard.agents.reasoner import ReasonerAgent
from visionguard.gateway.policy import PolicyDenied, PolicyGateway
from visionguard.pipeline import run_pipeline

DATASET_SEED = 20261023
IMAGES_DEFAULT = 200

# Same shape as PolicyGateway.DEFAULT_TENANT, but with a request budget
# high enough that the token bucket never denies during the run.
LOAD_TENANT_CONFIG = {
    "requests_per_minute": 10_000_000,
    "min_confidence": 0.60,
    "allowed_actions": ["log", "quarantine", "alert"],
    "enabled": True,
}


def build_components(audit_dir):
    gateway = PolicyGateway(
        tenants={"load-test": dict(LOAD_TENANT_CONFIG)},
        audit_path=os.path.join(audit_dir, "audit.log"))
    actor = ActorAgent(quarantine_dir=os.path.join(audit_dir, "quarantine"),
                       audit=gateway.audit)
    return (DetectorAgent(), ReasonerAgent(), actor, gateway)


def run_load(paths, audit_dir, tenant="load-test"):
    """Run the pipeline over every image path.

    Returns (latencies_ms, verdict_counts). Raises PolicyDenied if the
    gateway refuses a request; with the load-test tenant that means the
    bucket config is wrong and the numbers would be meaningless.
    """
    detector, reasoner, actor, gateway = build_components(audit_dir)
    latencies = []
    verdicts = {}
    # Warm-up: first call pays interpreter/cache warm-up cost; exclude it.
    run_pipeline(paths[0], tenant=tenant, detector=detector,
                 reasoner=reasoner, actor=actor, gateway=gateway)
    for path in paths:
        result = run_pipeline(path, tenant=tenant, detector=detector,
                              reasoner=reasoner, actor=actor,
                              gateway=gateway)
        latencies.append(result["latency_ms"])
        sev = result["verdict"]["severity"]
        verdicts[sev] = verdicts.get(sev, 0) + 1
    return latencies, verdicts


def compute_stats(latencies):
    """Percentiles and supporting numbers from a latency list."""
    lat = np.asarray(latencies, dtype=float)
    n = len(lat)
    mean = float(np.mean(lat)) if n else 0.0
    p50, p95 = (float(x) for x in np.percentile(lat, [50, 95])) if n else (0.0, 0.0)
    return {
        "n": n,
        "min_ms": round(float(np.min(lat)) if n else 0.0, 2),
        "max_ms": round(float(np.max(lat)) if n else 0.0, 2),
        "mean_ms": round(mean, 2),
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        # images per second = 1 / mean seconds per image
        "throughput_imgs_per_s": round(1000.0 / mean, 1) if mean else 0.0,
    }


def env_info():
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "opencv": cv2.__version__,
        "numpy": np.__version__,
        "torch": torch.__version__,
    }


def write_report(path, stats, verdicts, env, source, seed):
    lines = []
    lines.append("# VisionGuard Load Test")
    lines.append("")
    lines.append(f"Generated {date.today().isoformat()} by "
                 "`scripts/load_test.py`.")
    lines.append("")
    lines.append("## Method")
    lines.append("")
    lines.append(f"- Source: {source}; seed `{seed}`.")
    lines.append("- Full `run_pipeline` per image: gateway check, detector, "
                 "reasoner, verdict re-check, actor. One warm-up image ran "
                 "first and is excluded from the numbers.")
    lines.append("- Gateway tenant `load-test` runs with "
                 "`requests_per_minute=10_000_000`: the token bucket is "
                 "exercised on every request but never denies, so the "
                 "numbers reflect pipeline speed, not throttling.")
    lines.append("- LLM judge off (pipeline default). Audit log and "
                 "quarantine dir are fresh temp dirs per run.")
    lines.append("- p50/p95 via `numpy.percentile` (linear interpolation); "
                 "throughput derived from the mean latency.")
    lines.append("")
    lines.append("## Environment")
    lines.append("")
    lines.append(f"- Python {env['python']} on {env['platform']} "
                 f"({env['cpu_count']} CPUs)")
    lines.append(f"- opencv {env['opencv']}, numpy {env['numpy']}, "
                 f"torch {env['torch']}")
    lines.append("")
    lines.append("## Results")
    lines.append("")
    lines.append(f"Images: {stats['n']}")
    lines.append("")
    lines.append("| metric | value |")
    lines.append("|--------|-------|")
    lines.append(f"| p50 latency | {stats['p50_ms']} ms |")
    lines.append(f"| p95 latency | {stats['p95_ms']} ms |")
    lines.append(f"| mean latency | {stats['mean_ms']} ms |")
    lines.append(f"| min latency | {stats['min_ms']} ms |")
    lines.append(f"| max latency | {stats['max_ms']} ms |")
    lines.append(f"| throughput | {stats['throughput_imgs_per_s']} "
                 "images/s |")
    lines.append("")
    lines.append("Verdict mix during the run: "
                 + ", ".join(f"{k}: {v}" for k, v in sorted(verdicts.items())))
    lines.append("")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {path}")


def prepare_dataset(count, seed):
    out_dir = tempfile.mkdtemp(prefix="visionguard_load_")
    generate(count, out_dir, seed=seed)
    source = (f"{2 * count} synthetic images ({count} defective, "
              f"{count} clean, 640x480)")
    return out_dir, source


def collect_from_dir(image_dir):
    paths = sorted(os.path.join(image_dir, f) for f in os.listdir(image_dir)
                   if f.lower().endswith((".png", ".jpg", ".jpeg")))
    return paths, f"{len(paths)} images from {image_dir}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--images", type=int, default=IMAGES_DEFAULT,
                   help="total images to generate (ignored with --image-dir)")
    p.add_argument("--image-dir", default=None,
                   help="run on existing images instead of generating")
    p.add_argument("--seed", type=int, default=DATASET_SEED)
    p.add_argument("--out", default=os.path.join(REPO_ROOT, "docs",
                                                 "load_test.md"))
    a = p.parse_args()

    if a.image_dir:
        image_dir = a.image_dir
        source = f"{len(os.listdir(image_dir))} images from {image_dir}"
        paths, source = collect_from_dir(image_dir)
        if not paths:
            raise SystemExit(f"no images found in {image_dir}")
    else:
        per_class = max(1, a.images // 2)
        image_dir, source = prepare_dataset(per_class, a.seed)
        paths, _ = collect_from_dir(image_dir)

    print(f"running load test: {source}")
    audit_dir = tempfile.mkdtemp(prefix="visionguard_load_audit_")
    latencies, verdicts = run_load(paths, audit_dir)
    stats = compute_stats(latencies)
    print(f"n={stats['n']} p50={stats['p50_ms']}ms p95={stats['p95_ms']}ms "
          f"mean={stats['mean_ms']}ms "
          f"throughput={stats['throughput_imgs_per_s']}img/s")
    write_report(a.out, stats, verdicts, env_info(), source, a.seed)


if __name__ == "__main__":
    main()
