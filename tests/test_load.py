import os

from load_test import (build_components, collect_from_dir, compute_stats,
                       env_info, run_load, write_report)
from make_sample_images import generate


def test_compute_stats_known_values():
    latencies = [float(i) for i in range(1, 101)]
    s = compute_stats(latencies)
    assert s["n"] == 100
    assert s["p50_ms"] == 50.5
    assert s["p95_ms"] == 95.05
    assert s["min_ms"] == 1.0
    assert s["max_ms"] == 100.0
    assert s["mean_ms"] == 50.5
    assert s["throughput_imgs_per_s"] == round(1000.0 / 50.5, 1)


def test_compute_stats_empty():
    s = compute_stats([])
    assert s["n"] == 0
    assert s["p50_ms"] == 0.0
    assert s["p95_ms"] == 0.0


def test_run_load_small_set(tmp_path):
    img_dir = str(tmp_path / "imgs")
    generate(3, img_dir, seed=1234)
    paths, _ = collect_from_dir(img_dir)
    assert len(paths) == 6
    audit_dir = str(tmp_path / "audit")
    latencies, verdicts = run_load(paths, audit_dir)
    assert len(latencies) == 6
    assert all(l > 0 for l in latencies)
    assert sum(verdicts.values()) == 6
    # nothing quarantined outside the temp audit dir
    assert os.path.isdir(audit_dir)


def test_build_components_uses_high_rate_limit(tmp_path):
    detector, reasoner, actor, gateway = build_components(str(tmp_path))
    cfg = gateway.tenants["load-test"]
    assert cfg["requests_per_minute"] >= 1_000_000


def test_write_report_creates_file(tmp_path):
    out = str(tmp_path / "load_test.md")
    stats = compute_stats([10.0, 20.0, 30.0, 40.0])
    env = env_info()
    write_report(out, stats, {"none": 2, "major": 2}, env,
                 "4 synthetic images (2 defective, 2 clean, 640x480)",
                 seed=7)
    text = open(out).read()
    assert "p50 latency" in text
    assert "p95 latency" in text
    assert "numpy.percentile" in text
    assert "Verdict mix" in text
