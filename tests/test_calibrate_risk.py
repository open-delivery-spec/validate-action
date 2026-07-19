"""Tests for scripts/calibrate-risk.py"""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "calibrate_risk",
    Path(__file__).parent.parent / "scripts" / "calibrate-risk.py",
)
cr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cr)


class TestParseMarker:
    def test_parse_valid_marker(self):
        body = '<!-- ods-calibration {"version":1,"predicted_risk":"medium","predicted_tier":"standard"} -->'
        p = cr.parse_marker(body)
        assert p["predicted_risk"] == "medium"

    def test_parse_invalid_marker_returns_none(self):
        assert cr.parse_marker("no marker") is None
        assert cr.parse_marker("<!-- ods-calibration {bad json} -->") is None


class TestClassifyOutcome:
    def test_high_priority(self):
        assert cr.classify_outcome(["ods:outcome/incident"]) == "high"

    def test_medium_priority(self):
        assert cr.classify_outcome(["ods:outcome/rework"]) == "medium"

    def test_low_priority(self):
        assert cr.classify_outcome(["ods:outcome/clean"]) == "low"

    def test_unknown(self):
        assert cr.classify_outcome(["bug"]) is None


class TestMetrics:
    def test_metrics_and_matrix(self):
        rows = [
            {"predicted": "high", "actual": "high"},
            {"predicted": "high", "actual": "medium"},
            {"predicted": "medium", "actual": "high"},
            {"predicted": "low", "actual": "low"},
        ]
        m = cr.metrics(rows)
        mat = cr.calibration_matrix(rows)
        assert m["sample_count"] == 4
        assert m["predicted_high_count"] == 2
        assert m["actual_high_count"] == 2
        assert mat["high"]["high"] == 1
        assert mat["high"]["medium"] == 1

    def test_recommendation_insufficient_samples(self):
        rec = cr.recommendation({"sample_count": 3}, min_samples=20)
        assert "Need more labeled merged PR outcomes" in rec

    def test_markdown_render(self):
        report = {
            "window_days": 30,
            "matrix": {
                "low": {"low": 1, "medium": 0, "high": 0},
                "medium": {"low": 0, "medium": 1, "high": 1},
                "high": {"low": 0, "medium": 1, "high": 2},
            },
            "metrics": {
                "sample_count": 6,
                "exact_match": 0.67,
                "high_precision": 0.67,
                "high_recall": 0.67,
            },
            "recommendation": "Calibration looks stable.",
        }
        md = cr.build_markdown(report)
        assert "Risk Calibration" in md
        assert "Confusion Matrix" in md
        assert "Calibration looks stable." in md

