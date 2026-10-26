import os

import pytest

from make_sample_images import generate
from visionguard.agents.detector import DetectorAgent
from visionguard.agents.reasoner import ReasonerAgent


@pytest.fixture(scope="module")
def sample_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("samples")
    generate(5, str(d), seed=123)
    return d


def _one(detector, sample_dir, prefix):
    for name in sorted(os.listdir(sample_dir)):
        if name.startswith(prefix) and name.endswith(".png"):
            return os.path.join(sample_dir, name)
    raise AssertionError(f"no {prefix} sample generated")


def test_detector_finds_synthetic_defect(sample_dir):
    agent = DetectorAgent()
    for kind in ("scratch", "dent", "spots", "crack", "corrosion"):
        path = _one(agent, sample_dir, f"defective_{kind}")
        dets = agent.detect(path)
        assert len(dets) > 0, f"no detections in {path}"
        assert all(0.0 <= d.defect_score <= 1.0 for d in dets)


def test_detector_labels_each_defect_kind(sample_dir):
    agent = DetectorAgent()
    expected = {"scratch": "scratch", "dent": "dent", "spots": "spot",
                "crack": "crack", "corrosion": "corrosion"}
    for kind, label in expected.items():
        path = _one(agent, sample_dir, f"defective_{kind}")
        labels = {d.label for d in agent.detect(path)}
        assert label in labels, f"{path} labelled {labels}, not {label}"


def test_detector_clean_plate_has_no_detections(sample_dir):
    agent = DetectorAgent()
    for i in range(5):
        path = os.path.join(sample_dir, f"clean_{i:03d}.png")
        assert agent.detect(path) == [], f"false positive in {path}"


def test_detector_rejects_missing_file():
    agent = DetectorAgent()
    with pytest.raises(FileNotFoundError):
        agent.detect("/nonexistent/image.png")


def test_reasoner_severity_ordering():
    from visionguard.agents.detector import Detection
    reasoner = ReasonerAgent()
    mild = [Detection(bbox=(0, 0, 10, 10), area=100.0,
                      defect_score=0.4, label="spot")]
    severe = [Detection(bbox=(0, 0, 10, 10), area=100.0,
                        defect_score=0.95, label="scratch")]
    assert reasoner.reason(mild).severity == "minor"
    assert reasoner.reason(severe).severity == "critical"
    assert reasoner.reason([]).severity == "none"
