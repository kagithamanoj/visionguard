"""Generate a static HTML results viewer for VisionGuard inspections.

Runs the real pipeline (detect -> reason -> act through the policy
gateway) on every sample image, renders annotated copies with the
detection bounding boxes, and writes a self-contained static site into
``viewer/``:

    viewer/index.html            gallery of every inspected image
    viewer/<name>.html           per-image detail page
    viewer/assets/               original + annotated images

The index page summarizes the whole run: verdict mix, mean latency, and
the gateway metering (requests, denials, avg/p95 latency per tenant).
Regenerate with one command:

    python scripts/make_results_viewer.py [--images samples] [--out viewer]

Everything displayed comes from real pipeline runs, so the numbers match
the current code. Open viewer/index.html in any browser; no server needed.
"""
import argparse
import csv
import html
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from visionguard.agents.actor import ActorAgent  # noqa: E402
from visionguard.agents.detector import DetectorAgent  # noqa: E402
from visionguard.agents.reasoner import ReasonerAgent  # noqa: E402
from visionguard.gateway.policy import PolicyGateway  # noqa: E402
from visionguard.pipeline import run_pipeline  # noqa: E402

SEVERITY_COLOR = {  # CSS
    "none": "#2ea043",
    "minor": "#e3b341",
    "major": "#f0883e",
    "critical": "#f85149",
    "review": "#a371f7",
}

STYLE = """
body { font-family: -apple-system, "Segoe UI", sans-serif; background: #0d1117;
       color: #e6edf3; margin: 0; }
header { padding: 28px 32px; border-bottom: 1px solid #30363d; }
h1 { margin: 0 0 6px; font-size: 26px; }
.meta { color: #8b949e; font-size: 13px; }
.summary { display: flex; gap: 16px; flex-wrap: wrap; padding: 20px 32px; }
.card { background: #161b22; border: 1px solid #30363d; border-radius: 8px;
        padding: 14px 18px; min-width: 150px; }
.card .k { color: #8b949e; font-size: 12px; text-transform: uppercase; }
.card .v { font-size: 22px; font-weight: 600; margin-top: 4px; }
section { padding: 0 32px 24px; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #30363d; }
th { color: #8b949e; font-weight: 600; font-size: 12px; text-transform: uppercase; }
.badge { display: inline-block; padding: 3px 10px; border-radius: 12px;
         font-size: 12px; font-weight: 700; color: #fff; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
        gap: 18px; padding: 0 32px 32px; }
.tile { background: #161b22; border: 1px solid #30363d; border-radius: 8px;
        overflow: hidden; text-decoration: none; color: inherit; }
.tile img { width: 100%; display: block; }
.tile .info { padding: 10px 14px 14px; }
.tile .name { font-size: 14px; font-weight: 600; }
.tile .row { display: flex; justify-content: space-between; align-items: center;
             margin-top: 8px; font-size: 13px; color: #8b949e; }
.detail { display: grid; grid-template-columns: 1fr 380px; gap: 24px;
          padding: 24px 32px; }
.detail img.full { width: 100%; border: 1px solid #30363d; border-radius: 8px; }
.panel { background: #161b22; border: 1px solid #30363d; border-radius: 8px;
         padding: 18px 20px; margin-bottom: 16px; }
.panel h3 { margin: 0 0 10px; font-size: 15px; }
.panel p { font-size: 14px; line-height: 1.5; margin: 6px 0; }
.kv { display: flex; justify-content: space-between; font-size: 14px; padding: 4px 0; }
.kv .k { color: #8b949e; }
nav.pager { padding: 0 32px 32px; font-size: 14px; }
nav.pager a { color: #58a6ff; text-decoration: none; margin-right: 18px; }
a { color: #58a6ff; }
"""


def _esc(value):
    return html.escape(str(value))


def _badge(severity):
    color = SEVERITY_COLOR.get(severity, "#8b949e")
    return (f'<span class="badge" style="background:{color}">'
            f'{_esc(severity.upper())}</span>')


def collect_results(samples_dir):
    """Run the real pipeline on every labeled sample image.

    Quarantine copies and audit entries go to a temp dir so the viewer
    run does not touch the repo's working files.
    """
    labels = {}
    labels_path = os.path.join(samples_dir, "labels.csv")
    if os.path.exists(labels_path):
        with open(labels_path) as f:
            for row in csv.DictReader(f):
                labels[row["filename"]] = row["label"]

    names = sorted(n for n in os.listdir(samples_dir)
                   if n.lower().endswith(".png"))
    names.sort(key=lambda n: 0 if n.startswith("defective") else 1)

    tmp = tempfile.mkdtemp(prefix="visionguard_viewer_")
    gateway = PolicyGateway(
        tenants={"viewer": {"requests_per_minute": 6000,
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
        result = run_pipeline(path, tenant="viewer", detector=detector,
                              reasoner=reasoner, actor=actor,
                              gateway=gateway)
        result["label"] = labels.get(name, "unknown")
        results.append((path, result))
        print(f"{name}: verdict={result['verdict']['severity']} "
              f"conf={result['verdict']['confidence']:.2f} "
              f"latency={result['latency_ms']:.0f}ms")
    return results, gateway.get_metrics()


def annotate_image(src_path, detections, severity, dest_path):
    """Draw bounding boxes and labels; coordinates are in image pixels."""
    img = cv2.imread(src_path)
    if img is None:
        raise FileNotFoundError(f"cannot read image: {src_path}")
    css = SEVERITY_COLOR.get(severity, "#8b949e")
    bgr = tuple(int(css.lstrip("#")[i:i + 2], 16)
                for i in (4, 2, 0))
    for d in detections:
        x, y, w, h = [int(v) for v in d["bbox"]]
        cv2.rectangle(img, (x, y), (x + w, y + h), bgr, 3)
        tag = f"{d['label']} {d['defect_score']:.2f}"
        (tw, th), _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        ty = max(y - 8, th + 10)
        cv2.rectangle(img, (x, ty - th - 10), (x + tw + 10, ty), bgr, -1)
        cv2.putText(img, tag, (x + 5, ty - 5), cv2.FONT_HERSHEY_SIMPLEX,
                    0.7, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.imwrite(dest_path, img)


def _page(title, body, style=STYLE):
    return (f"<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
            f"<meta charset=\"utf-8\">\n"
            f"<meta name=\"viewport\" content=\"width=device-width, "
            f"initial-scale=1\">\n<title>{_esc(title)}</title>\n"
            f"<style>{style}</style>\n</head>\n<body>\n{body}\n</body>\n"
            f"</html>\n")


def render_index(collected, metrics, generated_at, out_dir):
    mix = {}
    for _, r in collected:
        sev = r["verdict"]["severity"]
        mix[sev] = mix.get(sev, 0) + 1
    mean_ms = sum(r["latency_ms"] for _, r in collected) / len(collected)
    total_det = sum(len(r["detections"]) for _, r in collected)

    mix_str = ", ".join(f"{s}: {n}" for s, n in sorted(mix.items()))

    tiles = []
    for img_path, r in collected:
        name = os.path.basename(img_path)
        stem = os.path.splitext(name)[0]
        sev = r["verdict"]["severity"]
        conf = r["verdict"]["confidence"]
        tiles.append(
            f'<a class="tile" href="{_esc(stem)}.html">'
            f'<img src="assets/annotated_{_esc(name)}" '
            f'alt="{_esc(name)}">'
            f'<div class="info"><div class="name">{_esc(name)}</div>'
            f'<div class="row">{_badge(sev)}'
            f'<span>{len(r["detections"])} detections, '
            f'{conf:.2f} conf</span></div>'
            f'<div class="row"><span>expected: '
            f'{_esc(r["label"])}</span>'
            f'<span>{r["latency_ms"]:.0f} ms</span></div>'
            f'</div></a>')

    meter_rows = []
    for tenant, m in metrics.items():
        by_sev = ", ".join(f"{s}: {n}"
                           for s, n in sorted(m["by_severity"].items()))
        meter_rows.append(
            f"<tr><td>{_esc(tenant)}</td><td>{m['requests']}</td>"
            f"<td>{m['denied']}</td>"
            f"<td>{_esc(by_sev or 'none')}</td>"
            f"<td>{m['avg_latency_ms']:.1f}</td>"
            f"<td>{m['p95_latency_ms']:.1f}</td></tr>")

    body = (
        f"<header><h1>VisionGuard inspection results</h1>"
        f"<div class=\"meta\">generated {generated_at} from a live "
        f"pipeline run over {len(collected)} sample images. "
        f"Verdicts, latencies, and metering below are the actual "
        f"pipeline outputs.</div></header>"
        f"<div class=\"summary\">"
        f"<div class=\"card\"><div class=\"k\">Images inspected</div>"
        f"<div class=\"v\">{len(collected)}</div></div>"
        f"<div class=\"card\"><div class=\"k\">Mean latency</div>"
        f"<div class=\"v\">{mean_ms:.0f} ms</div></div>"
        f"<div class=\"card\"><div class=\"k\">Total detections</div>"
        f"<div class=\"v\">{total_det}</div></div>"
        f"<div class=\"card\"><div class=\"k\">Verdict mix</div>"
        f"<div class=\"v\" style=\"font-size:15px\">{_esc(mix_str)}</div>"
        f"</div></div>"
        f"<section><h2>Gateway metering</h2>"
        f"<table><tr><th>Tenant</th><th>Requests</th><th>Denied</th>"
        f"<th>Verdicts</th><th>Avg latency (ms)</th>"
        f"<th>p95 latency (ms)</th></tr>"
        f"{''.join(meter_rows)}</table></section>"
        f"<div class=\"grid\">{''.join(tiles)}</div>"
    )
    with open(os.path.join(out_dir, "index.html"), "w") as f:
        f.write(_page("VisionGuard inspection results", body))


def render_detail(img_path, result, prev_stem, next_stem, out_dir):
    name = os.path.basename(img_path)
    stem = os.path.splitext(name)[0]
    verdict = result["verdict"]
    det_rows = []
    for d in result["detections"]:
        x, y, w, h = [int(v) for v in d["bbox"]]
        det_rows.append(
            f"<tr><td>{_esc(d['label'])}</td>"
            f"<td>({x}, {y}, {w}, {h})</td>"
            f"<td>{d['area']:.1f}</td>"
            f"<td>{d['defect_score']:.3f}</td></tr>")
    det_table = (
        "<table><tr><th>Label</th><th>BBox (x, y, w, h)</th>"
        "<th>Area</th><th>Defect score</th></tr>"
        f"{''.join(det_rows)}</table>"
    ) if det_rows else "<p>No defects detected.</p>"

    actions = result["actions"].get("actions", [])
    pager = []
    if prev_stem:
        pager.append(f'<a href="{_esc(prev_stem)}.html">&larr; previous</a>')
    pager.append('<a href="index.html">gallery</a>')
    if next_stem:
        pager.append(f'<a href="{_esc(next_stem)}.html">next &rarr;</a>')

    body = (
        f"<header><h1>{_esc(name)}</h1>"
        f"<div class=\"meta\">expected label: {_esc(result['label'])} | "
        f"tenant: {_esc(result['tenant'])} | "
        f"latency: {result['latency_ms']:.1f} ms</div></header>"
        f"<div class=\"detail\">"
        f"<img class=\"full\" src=\"assets/annotated_{_esc(name)}\" "
        f"alt=\"{ _esc(name)} with detection boxes\">"
        f"<div>"
        f"<div class=\"panel\"><h3>Verdict</h3>"
        f"<p>{_badge(verdict['severity'])} "
        f"confidence {verdict['confidence']:.3f}</p>"
        f"<p>{_esc(verdict['rationale'])}</p>"
        f"<div class=\"kv\"><span class=\"k\">Detections</span>"
        f"<span>{verdict['detection_count']}</span></div>"
        f"<div class=\"kv\"><span class=\"k\">Max defect score</span>"
        f"<span>{verdict['max_defect_score']:.3f}</span></div>"
        f"</div>"
        f"<div class=\"panel\"><h3>Actions taken</h3>"
        f"<p>{_esc(', '.join(actions) or 'none')}</p></div>"
        f"<div class=\"panel\"><h3>Detections</h3>{det_table}</div>"
        f"</div></div>"
        f"<nav class=\"pager\">{''.join(pager)}</nav>"
    )
    with open(os.path.join(out_dir, f"{stem}.html"), "w") as f:
        f.write(_page(f"VisionGuard: {name}", body))


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--images", default="samples",
                   help="directory of sample images (default: samples)")
    p.add_argument("--out", default="viewer",
                   help="output directory for the static site")
    a = p.parse_args()

    if os.path.exists(a.out):
        shutil.rmtree(a.out)
    assets = os.path.join(a.out, "assets")
    os.makedirs(assets, exist_ok=True)

    collected, metrics = collect_results(a.images)
    if not collected:
        raise SystemExit(f"no PNG images found in {a.images}")

    stems = []
    for img_path, result in collected:
        name = os.path.basename(img_path)
        shutil.copy2(img_path, os.path.join(assets, name))
        annotate_image(img_path, result["detections"],
                       result["verdict"]["severity"],
                       os.path.join(assets, f"annotated_{name}"))
        stems.append(os.path.splitext(name)[0])

    for i, (img_path, result) in enumerate(collected):
        prev_stem = stems[i - 1] if i > 0 else None
        next_stem = stems[i + 1] if i < len(stems) - 1 else None
        render_detail(img_path, result, prev_stem, next_stem, a.out)

    generated_at = datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC")
    render_index(collected, metrics, generated_at, a.out)
    print(f"wrote viewer site to {a.out}/ "
          f"({len(collected)} images, {len(stems)} detail pages)")


if __name__ == "__main__":
    main()
