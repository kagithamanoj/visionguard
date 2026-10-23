# VisionGuard Load Test

Generated 2026-10-23 by `scripts/load_test.py`.

## Method

- Source: 200 synthetic images (100 defective, 100 clean, 640x480); seed `20261023`.
- Full `run_pipeline` per image: gateway check, detector, reasoner, verdict re-check, actor. One warm-up image ran first and is excluded from the numbers.
- Gateway tenant `load-test` runs with `requests_per_minute=10_000_000`: the token bucket is exercised on every request but never denies, so the numbers reflect pipeline speed, not throttling.
- LLM judge off (pipeline default). Audit log and quarantine dir are fresh temp dirs per run.
- p50/p95 via `numpy.percentile` (linear interpolation); throughput derived from the mean latency.

## Environment

- Python 3.12.3 on Linux-7.0.0-39-generic-x86_64-with-glibc2.39 (2 CPUs)
- opencv 5.0.0, numpy 2.5.3, torch 2.14.1+cpu

## Results

Images: 200

| metric | value |
|--------|-------|
| p50 latency | 11.22 ms |
| p95 latency | 19.0 ms |
| mean latency | 12.32 ms |
| min latency | 7.65 ms |
| max latency | 50.41 ms |
| throughput | 81.2 images/s |

Verdict mix during the run: critical: 1, major: 61, none: 100, review: 38

