"""Tests for scripts/generate-report.py"""
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Load module whose filename has a hyphen (not a valid Python identifier).
_spec = importlib.util.spec_from_file_location(
    "generate_report",
    Path(__file__).parent.parent / "scripts" / "generate-report.py",
)
gr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gr)


# ── load_json ─────────────────────────────────────────────────────────────────

class TestLoadJson:
    def test_valid_file(self, tmp_path):
        f = tmp_path / "x.json"
        f.write_text('{"k": 1}')
        assert gr.load_json(str(f)) == {"k": 1}

    def test_missing_file_returns_empty_dict(self, tmp_path):
        assert gr.load_json(str(tmp_path / "nope.json")) == {}

    def test_invalid_json_returns_empty_dict(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("not json {{{")
        assert gr.load_json(str(f)) == {}


# ── coverage_label ────────────────────────────────────────────────────────────

class TestCoverageLabel:
    @pytest.mark.parametrize("val,expected", [
        (-1.0,  "N/A"),   # ODS sentinel: not measured
        (-0.01, "N/A"),   # any negative → N/A
        (0.0,   "0%"),
        (0.756, "76%"),   # rounds to nearest integer
        (1.0,   "100%"),
        (0,     "0%"),    # integer zero is fine
    ])
    def test_numeric(self, val, expected):
        assert gr.coverage_label(val) == expected

    def test_non_numeric_string_is_na(self):
        assert gr.coverage_label("bad") == "N/A"

    def test_none_is_na(self):
        assert gr.coverage_label(None) == "N/A"

    def test_sentinel_never_produces_minus_100(self):
        # Regression: before the fix, -1.0 rendered as "-100%"
        assert "-100" not in gr.coverage_label(-1.0)


# ── md_cell ───────────────────────────────────────────────────────────────────

class TestMdCell:
    def test_pipe_escaped(self):
        assert gr.md_cell("foo|bar") == r"foo\|bar"

    def test_newline_collapsed(self):
        assert gr.md_cell("line1\nline2") == "line1 line2"

    def test_carriage_return_collapsed(self):
        assert gr.md_cell("a\rb") == "a b"

    def test_backslash_escaped(self):
        assert gr.md_cell("a\\b") == "a\\\\b"

    def test_plain_text_unchanged(self):
        assert gr.md_cell("hello") == "hello"

    def test_non_string_converted(self):
        assert gr.md_cell(42) == "42"


# ── h (HTML escape) ───────────────────────────────────────────────────────────

class TestH:
    def test_lt_gt_escaped(self):
        out = gr.h("<b>")
        assert "&lt;" in out
        assert "&gt;" in out

    def test_ampersand_escaped(self):
        assert "&amp;" in gr.h("a & b")

    def test_double_quote_escaped(self):
        assert "&quot;" in gr.h('"hi"')

    def test_plain_passthrough(self):
        assert gr.h("hello") == "hello"


# ── build_svg ─────────────────────────────────────────────────────────────────

class TestBuildSvg:
    @pytest.mark.parametrize("result,color,label", [
        ("pass",  "#2ea043", "PASS"),
        ("warn",  "#d29922", "WARN"),
        ("block", "#cf222e", "BLOCK"),
    ])
    def test_known_result(self, result, color, label):
        svg = gr.build_svg(result, 0.0, 0.0)
        assert color in svg
        assert label in svg

    def test_unknown_result_fallback_color(self):
        svg = gr.build_svg("unknown", 0.0, 0.0)
        assert "#6e7681" in svg

    def test_meta_shows_confidence_and_debt(self):
        svg = gr.build_svg("pass", 0.75, 1.5)
        assert "75%" in svg
        assert "+1.5" in svg

    def test_negative_debt_sign(self):
        svg = gr.build_svg("pass", 0.0, -2.3)
        assert "-2.3" in svg

    def test_valid_svg_root_element(self):
        svg = gr.build_svg("warn", 0.5, 3.0)
        assert svg.startswith("<svg")
        assert "</svg>" in svg


# ── Helpers: minimal fixture data ─────────────────────────────────────────────

_D_HUMAN = {
    "ai_generated": False, "confidence": 0.0,
    "summary": "No AI", "evidence": [], "sources": [], "files": [],
}
_A_CLEAN = {
    "total_lines": 100, "ai_lines": 0,
    "issues": [], "summary": "No issues",
}
_S_NEUTRAL = {
    "technical_debt_delta": 0.3, "verdict": "neutral",
    "recommendation": "Review recommended", "files_analyzed": 5,
    "breakdown": {
        "ai_code_ratio": 0.0, "defect_density": 0.0,
        "critical_issues": 0, "test_coverage": -1.0,
        "duplication_rate": 0.0,
    },
}
_C_ALLOW = {"allowed": True, "denials": [], "warnings": []}


def _run(detect, analyze, score, check):
    """Run main() in a temp dir; return (result, ods_report_dict, summary_md, gh_output_lines)."""
    with tempfile.TemporaryDirectory() as d:
        for name, data in [("detect", detect), ("analyze", analyze),
                           ("score", score), ("check", check)]:
            Path(d, f"{name}.json").write_text(json.dumps(data))

        github_output = os.path.join(d, "gh_output.txt")

        orig_argv = sys.argv[:]
        orig_env = dict(os.environ)
        sys.argv = ["generate-report.py", d, github_output]
        # prevent accidental writes to a real GITHUB_STEP_SUMMARY
        os.environ.pop("GITHUB_STEP_SUMMARY", None)
        try:
            result = gr.main()
        finally:
            sys.argv[:] = orig_argv
            os.environ.clear()
            os.environ.update(orig_env)

        report = json.loads(Path(d, "ods-report.json").read_text())
        md = Path(d, "ods-summary.md").read_text()
        gh_lines = (
            Path(github_output).read_text().splitlines()
            if os.path.exists(github_output)
            else []
        )
        return result, report, md, gh_lines


# ── Result determination ──────────────────────────────────────────────────────

class TestResultDetermination:
    def test_clean_human_pr_is_pass(self):
        result, _, _, _ = _run(_D_HUMAN, _A_CLEAN, _S_NEUTRAL, _C_ALLOW)
        assert result == "pass"

    def test_policy_block_overrides_everything(self):
        check = {**_C_ALLOW, "allowed": False, "denials": ["Too much debt"]}
        result, _, _, _ = _run(_D_HUMAN, _A_CLEAN, _S_NEUTRAL, check)
        assert result == "block"

    def test_detect_error_is_warn(self):
        detect = {**_D_HUMAN, "_ods_detect_error": True}
        result, _, _, _ = _run(detect, _A_CLEAN, _S_NEUTRAL, _C_ALLOW)
        assert result == "warn"

    def test_ai_detected_is_warn(self):
        detect = {**_D_HUMAN, "ai_generated": True, "confidence": 0.9}
        result, _, _, _ = _run(detect, _A_CLEAN, _S_NEUTRAL, _C_ALLOW)
        assert result == "warn"

    def test_block_beats_detect_error(self):
        detect = {**_D_HUMAN, "_ods_detect_error": True}
        check = {**_C_ALLOW, "allowed": False, "denials": ["blocked"]}
        result, _, _, _ = _run(detect, _A_CLEAN, _S_NEUTRAL, check)
        assert result == "block"


# ── GitHub step outputs ───────────────────────────────────────────────────────

class TestGithubOutputs:
    def setup_method(self):
        _, _, _, self.lines = _run(_D_HUMAN, _A_CLEAN, _S_NEUTRAL, _C_ALLOW)

    def test_all_required_keys_written(self):
        keys = {ln.split("=", 1)[0] for ln in self.lines if "=" in ln}
        assert {"result", "ai_detected", "ai_confidence", "tech_debt_delta", "policy_allowed"} <= keys

    def test_pass_result_value(self):
        assert "result=pass" in self.lines

    def test_block_result_value(self):
        check = {**_C_ALLOW, "allowed": False, "denials": ["x"]}
        _, _, _, lines = _run(_D_HUMAN, _A_CLEAN, _S_NEUTRAL, check)
        assert "result=block" in lines

    def test_ai_detected_false(self):
        assert "ai_detected=false" in self.lines

    def test_policy_allowed_true(self):
        assert "policy_allowed=true" in self.lines


# ── ods-report.json structure ─────────────────────────────────────────────────

class TestReportJson:
    def setup_method(self):
        _, self.report, _, _ = _run(_D_HUMAN, _A_CLEAN, _S_NEUTRAL, _C_ALLOW)

    def test_top_level_keys(self):
        for key in ("result", "ai_detected", "ai_confidence", "analysis", "score", "policy", "risk_brief"):
            assert key in self.report

    def test_result_matches(self):
        assert self.report["result"] == "pass"

    def test_analysis_issue_count(self):
        assert self.report["analysis"]["total_issues"] == 0

    def test_policy_section(self):
        assert self.report["policy"]["allowed"] is True
        assert self.report["policy"]["denials"] == []

    def test_risk_brief_defaults_present(self):
        rb = self.report["risk_brief"]
        assert rb["level"] in {"low", "medium", "high"}
        assert isinstance(rb["reasons"], list)
        assert rb["recommended_action"]


# ── build_markdown ────────────────────────────────────────────────────────────

_MD_BASE = dict(
    overall="✅ PASS", result_value="pass",
    detect_error=False, ai_detected=False, ai_confidence=0.0,
    tech_debt=0.3, verdict="neutral", recommendation="Review recommended",
    policy_allowed=True, evidence=[], analyze_summary="No issues",
    issues=[],
    score={"breakdown": {
        "ai_code_ratio": 0.0, "defect_density": 0.0, "critical_issues": 0,
        "test_coverage": -1.0, "duplication_rate": 0.0,
    }},
    denials=[], warnings_list=[], files=[],
)


class TestBuildMarkdown:
    def test_html_comment_marker_present(self):
        md = gr.build_markdown(**_MD_BASE)
        assert "<!-- ods-compliance-report -->" in md
        assert "Risk Brief" in md

    def test_coverage_not_measured_shows_na(self):
        md = gr.build_markdown(**_MD_BASE)
        assert "N/A" in md
        assert "-100" not in md

    def test_coverage_percentage_shown_when_measured(self):
        kw = dict(_MD_BASE)
        kw["score"] = {"breakdown": {**_MD_BASE["score"]["breakdown"], "test_coverage": 0.75}}
        md = gr.build_markdown(**kw)
        assert "75%" in md

    def test_evidence_table_rendered(self):
        kw = dict(_MD_BASE, evidence=[
            {"source": "Co-Authored-By", "value": "Claude", "confidence": 0.9}
        ])
        md = gr.build_markdown(**kw)
        assert "Co-Authored-By" in md
        assert "90%" in md

    def test_no_evidence_shows_fallback(self):
        md = gr.build_markdown(**_MD_BASE)
        assert "No AI code detected." in md

    def test_issues_capped_at_10_with_overflow_note(self):
        issues = [
            {"rule": f"rule-{i}", "file": f"f{i}.go", "severity": "medium", "message": "msg"}
            for i in range(15)
        ]
        md = gr.build_markdown(**dict(_MD_BASE, issues=issues))
        assert "5 more" in md

    def test_policy_denials_section_present(self):
        kw = dict(_MD_BASE, denials=["Too much debt"],
                  policy_allowed=False, overall="❌ BLOCK", result_value="block")
        md = gr.build_markdown(**kw)
        assert "Too much debt" in md

    def test_no_denials_no_policy_section(self):
        md = gr.build_markdown(**_MD_BASE)
        assert "Policy Denials" not in md

    def test_policy_warnings_section(self):
        kw = dict(_MD_BASE, warnings_list=["Consider adding tests"])
        md = gr.build_markdown(**kw)
        assert "Consider adding tests" in md

    def test_detect_error_inconclusive_notice(self):
        kw = dict(_MD_BASE, detect_error=True,
                  overall="⚠️  WARN", result_value="warn")
        md = gr.build_markdown(**kw)
        assert "inconclusive" in md.lower()

    def test_files_table_rendered(self):
        kw = dict(_MD_BASE, files=[
            {"path": "main.go", "ai_lines": 50, "total_lines": 100, "confidence": 0.8}
        ])
        md = gr.build_markdown(**kw)
        assert "main.go" in md
        assert "80%" in md

    def test_pipe_in_message_escaped(self):
        issues = [{"rule": "r", "file": "f.go", "severity": "low", "message": "a|b"}]
        md = gr.build_markdown(**dict(_MD_BASE, issues=issues))
        # raw pipe would break the table; it must be escaped
        assert r"a\|b" in md


# ── build_html ────────────────────────────────────────────────────────────────

_HTML_BASE = dict(
    result_value="pass", overall="✅ PASS",
    detect_error=False, ai_detected=False, ai_confidence=0.0,
    tech_debt=0.3, verdict="neutral", policy_allowed=True,
    evidence=[], analyze_summary="No issues", issues=[],
    score={"breakdown": {
        "ai_code_ratio": 0.0, "defect_density": 0.0, "critical_issues": 0,
        "test_coverage": -1.0, "duplication_rate": 0.0,
    }},
)


class TestBuildHtml:
    def test_valid_html_root(self):
        out = gr.build_html(**_HTML_BASE)
        assert "<!DOCTYPE html>" in out
        assert "</html>" in out
        assert "Risk Brief" in out

    def test_coverage_not_measured_shows_na(self):
        out = gr.build_html(**_HTML_BASE)
        assert "N/A" in out
        assert "-100" not in out

    def test_pass_result_class(self):
        out = gr.build_html(**_HTML_BASE)
        assert 'class="result pass"' in out

    def test_warn_result_class(self):
        kw = dict(_HTML_BASE, result_value="warn", overall="⚠️ WARN")
        assert 'class="result warn"' in gr.build_html(**kw)

    def test_block_result_class(self):
        kw = dict(_HTML_BASE, result_value="block", overall="❌ BLOCK")
        assert 'class="result block"' in gr.build_html(**kw)

    def test_detect_error_shows_inconclusive(self):
        kw = dict(_HTML_BASE, detect_error=True)
        assert "inconclusive" in gr.build_html(**kw).lower()

    def test_evidence_rows_rendered(self):
        kw = dict(_HTML_BASE, evidence=[
            {"source": "Co-Authored-By", "value": "Claude", "confidence": 0.85}
        ])
        out = gr.build_html(**kw)
        assert "Co-Authored-By" in out
        assert "85%" in out

    def test_issue_rows_rendered(self):
        kw = dict(_HTML_BASE, issues=[
            {"rule": "ai-over-commenting", "file": "main.go",
             "severity": "high", "message": "Too many comments"}
        ])
        out = gr.build_html(**kw)
        assert "ai-over-commenting" in out
        assert "Too many comments" in out

    def test_xss_in_issue_message_escaped(self):
        kw = dict(_HTML_BASE, issues=[
            {"rule": "r", "file": "f.go", "severity": "low",
             "message": "<script>alert(1)</script>"}
        ])
        out = gr.build_html(**kw)
        assert "<script>" not in out
        assert "&lt;script&gt;" in out

    def test_coverage_percentage_shown_in_bar(self):
        kw = dict(_HTML_BASE, score={"breakdown": {
            **_HTML_BASE["score"]["breakdown"], "test_coverage": 0.63
        }})
        out = gr.build_html(**kw)
        assert "63%" in out


# ── review_tier plumbing ──────────────────────────────────────────────────────

class TestReviewTier:
    def test_tier_from_check_json_reaches_output_and_markdown(self):
        check = {"allowed": True, "review_tier": "auto", "denials": [], "warnings": []}
        _, report, md, gh = _run(_D_HUMAN, _A_CLEAN, _S_NEUTRAL, check)
        assert "review_tier=auto" in gh
        assert report["policy"]["review_tier"] == "auto"
        assert "**Review Tier:**" in md and "auto" in md

    def test_missing_tier_defaults_to_standard(self):
        _, report, md, gh = _run(_D_HUMAN, _A_CLEAN, _S_NEUTRAL, _C_ALLOW)
        assert "review_tier=standard" in gh
        assert report["policy"]["review_tier"] == "standard"

    def test_blocked_pr_hides_tier_in_markdown(self):
        check = {"allowed": False, "review_tier": "auto",
                 "denials": ["critical issue"], "warnings": []}
        _, report, md, gh = _run(_D_HUMAN, _A_CLEAN, _S_NEUTRAL, check)
        # Output still carries the raw value for tooling…
        assert "review_tier=auto" in gh
        # …but a blocked PR is never routed in the human-facing summary.
        assert "**Review Tier:**" not in md


# ── Risk brief behavior ────────────────────────────────────────────────────────

class TestRiskBrief:
    def test_blocked_is_high_risk(self):
        detect = {**_D_HUMAN, "ai_generated": True, "confidence": 0.95}
        analyze = {
            **_A_CLEAN,
            "issues": [{"rule": "x", "file": "a.go", "severity": "high", "message": "bad"}],
            "summary": "1 issue(s) found: 1 high",
        }
        check = {"allowed": False, "denials": ["critical policy fail"], "warnings": []}
        _, report, md, _ = _run(detect, analyze, _S_NEUTRAL, check)
        assert report["risk_brief"]["level"] == "high"
        assert "Risk Level" in md and "high" in md.lower()

    def test_clean_human_pr_is_low_risk(self):
        _, report, md, _ = _run(_D_HUMAN, _A_CLEAN, _S_NEUTRAL, _C_ALLOW)
        assert report["risk_brief"]["level"] == "low"
        assert "Low review risk" in report["risk_brief"]["recommended_action"]
