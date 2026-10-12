import os

from tune_detector import DEFECT_KINDS, build_eval_set, evaluate, grid_search
from visionguard.agents.detector import DetectorAgent


def test_evaluate_returns_sane_metrics(tmp_path):
    items = build_eval_set(2, seed=7)
    metrics = evaluate(DetectorAgent(), items)
    assert set(metrics["per_kind"]) == set(DEFECT_KINDS)
    for k in DEFECT_KINDS:
        row = metrics["per_kind"][k]
        assert row["n"] == 2
        assert 0.0 <= row["detection_recall"] <= 1.0
        assert 0.0 <= row["label_accuracy"] <= 1.0
    assert 0.0 <= metrics["precision"] <= 1.0
    assert 0.0 <= metrics["recall"] <= 1.0
    assert 0.0 <= metrics["fp_rate"] <= 1.0


def test_grid_search_sorts_by_score(tmp_path):
    items = build_eval_set(2, seed=7)
    small_grid = {"defect_contrast": [25, 70], "min_area": [80.0]}
    rows = grid_search(items, small_grid)
    assert len(rows) == 2
    scores = [m["score"] for _, m in rows]
    assert scores == sorted(scores, reverse=True)
