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


def _run(detect, analyze, score, check, extra_files=None):
    """Run main() in a temp dir; return (result, ods_report_dict, summary_md, gh_output_lines).

    extra_files: optional {filename: dict} written alongside the stage JSONs
    (e.g. ai-review-0.json verdict files).
    """
    with tempfile.TemporaryDirectory() as d:
        for name, data in [("detect", detect), ("analyze", analyze),
                           ("score", score), ("check", check)]:
            Path(d, f"{name}.json").write_text(json.dumps(data))
        for name, data in (extra_files or {}).items():
            Path(d, name).write_text(json.dumps(data))

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
        for key in ("result", "ai_detected", "ai_confidence", "analysis", "score", "policy"):
            assert key in self.report

    def test_result_matches(self):
        assert self.report["result"] == "pass"

    def test_analysis_issue_count(self):
        assert self.report["analysis"]["total_issues"] == 0

    def test_policy_section(self):
        assert self.report["policy"]["allowed"] is True
        assert self.report["policy"]["denials"] == []


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


# ── AI review verdicts ────────────────────────────────────────────────────────

_VERDICT_RC = {
    "schema": "ods.dev/review-verdict/v1",
    "reviewer": {"tool": "claude-code", "model": "claude-sonnet-4-5"},
    "verdict": "request_changes",
    "findings": [
        {"file": "svc.go", "line": 42, "severity": "high",
         "category": "correctness", "message": "expiry uses local | time"},
    ],
}


class TestAIReviewSection:
    def test_verdict_file_renders_section_and_report_json(self):
        _, report, md, _ = _run(_D_HUMAN, _A_CLEAN, _S_NEUTRAL, _C_ALLOW,
                                extra_files={"ai-review-0.json": _VERDICT_RC})
        assert "### 🧠 AI Review" in md
        assert "claude-code (claude-sonnet-4-5)" in md
        assert "request_changes" in md
        assert "svc.go:42" in md
        # pipe in the finding message must not break the table
        assert "expiry uses local \\| time" in md
        assert "advisory" in md
        assert report["ai_reviews"][0]["verdict"] == "request_changes"

    def test_multiple_reviewers_all_listed(self):
        approve = {**_VERDICT_RC, "verdict": "approve", "findings": [],
                   "reviewer": {"tool": "coderabbit"}}
        _, report, md, _ = _run(_D_HUMAN, _A_CLEAN, _S_NEUTRAL, _C_ALLOW,
                                extra_files={"ai-review-0.json": _VERDICT_RC,
                                             "ai-review-1.json": approve})
        assert "claude-code" in md and "coderabbit" in md
        assert len(report["ai_reviews"]) == 2

    def test_no_verdict_files_no_section(self):
        _, report, md, _ = _run(_D_HUMAN, _A_CLEAN, _S_NEUTRAL, _C_ALLOW)
        assert "AI Review" not in md
        assert report["ai_reviews"] == []

    def test_unparseable_verdict_skipped(self):
        _, report, md, _ = _run(_D_HUMAN, _A_CLEAN, _S_NEUTRAL, _C_ALLOW,
                                extra_files={"ai-review-0.json": {"not": "a verdict"}})
        assert "AI Review" not in md
        assert report["ai_reviews"] == []

    def test_verdict_never_changes_result(self):
        result, _, _, _ = _run(_D_HUMAN, _A_CLEAN, _S_NEUTRAL, _C_ALLOW,
                               extra_files={"ai-review-0.json": _VERDICT_RC})
        assert result == "pass"


# ── Merge-confidence section ──────────────────────────────────────────────────

class TestMergeConfidenceSection:
    def test_rendered_from_check_output(self):
        check = {**_C_ALLOW, "merge_confidence": {
            "files_changed": 1, "source_files_changed": 1, "test_files_changed": 0,
            "net_added_lines": 40, "tests_touched": False,
            "added_source_without_tests": True, "risky_paths": [".github/workflows/ci.yml"],
        }}
        _, report, md, _ = _run(_D_HUMAN, _A_CLEAN, _S_NEUTRAL, check)
        assert "Merge Confidence" in md
        assert "Source added without tests" in md
        assert ".github/workflows/ci.yml" in md
        assert report["merge_confidence"]["added_source_without_tests"] is True

    def test_absent_when_check_has_none(self):
        # Older CLIs don't echo merge_confidence — the section is skipped.
        _, report, md, _ = _run(_D_HUMAN, _A_CLEAN, _S_NEUTRAL, _C_ALLOW)
        assert "Merge Confidence" not in md
        assert report["merge_confidence"] == {}

    def test_pipe_in_risky_path_escaped(self):
        check = {**_C_ALLOW, "merge_confidence": {
            "files_changed": 1, "tests_touched": True,
            "added_source_without_tests": False, "risky_paths": ["weird|name.tf"],
        }}
        _, _, md, _ = _run(_D_HUMAN, _A_CLEAN, _S_NEUTRAL, check)
        assert "weird\\|name.tf" in md

    def test_never_changes_result(self):
        check = {**_C_ALLOW, "merge_confidence": {"added_source_without_tests": True}}
        result, _, _, _ = _run(_D_HUMAN, _A_CLEAN, _S_NEUTRAL, check)
        assert result == "pass"

    def test_patch_coverage_rendered_when_measured(self):
        check = {**_C_ALLOW,
                 "merge_confidence": {"tests_touched": True, "added_source_without_tests": False},
                 "patch_coverage": 0.4}
        _, report, md, _ = _run(_D_HUMAN, _A_CLEAN, _S_NEUTRAL, check)
        assert "Patch coverage (added lines)" in md
        assert "40%" in md
        assert report["patch_coverage"] == 0.4

    def test_patch_coverage_absent_when_not_measured(self):
        # -1 sentinel: not measured → no patch-coverage row.
        check = {**_C_ALLOW,
                 "merge_confidence": {"tests_touched": True},
                 "patch_coverage": -1}
        _, report, md, _ = _run(_D_HUMAN, _A_CLEAN, _S_NEUTRAL, check)
        assert "Patch coverage (added lines)" not in md
        assert report["patch_coverage"] == -1

    def test_patch_coverage_section_shown_without_merge_confidence(self):
        # Even if merge_confidence is empty, a measured patch coverage renders
        # the Merge Confidence section.
        check = {**_C_ALLOW, "patch_coverage": 0.9}
        _, _, md, _ = _run(_D_HUMAN, _A_CLEAN, _S_NEUTRAL, check)
        assert "Merge Confidence" in md
        assert "90%" in md

    def test_patch_coverage_never_changes_result(self):
        check = {**_C_ALLOW, "patch_coverage": 0.1}
        result, _, _, _ = _run(_D_HUMAN, _A_CLEAN, _S_NEUTRAL, check)
        assert result == "pass"

    def test_mutation_score_rendered_when_measured(self):
        check = {**_C_ALLOW,
                 "merge_confidence": {"tests_touched": True, "added_source_without_tests": False},
                 "mutation_score": 0.3}
        _, report, md, _ = _run(_D_HUMAN, _A_CLEAN, _S_NEUTRAL, check)
        assert "Mutation score (added lines)" in md
        assert "30%" in md
        assert report["mutation_score"] == 0.3

    def test_mutation_score_absent_when_not_measured(self):
        # -1 sentinel: not measured → no mutation-score row.
        check = {**_C_ALLOW,
                 "merge_confidence": {"tests_touched": True},
                 "mutation_score": -1}
        _, report, md, _ = _run(_D_HUMAN, _A_CLEAN, _S_NEUTRAL, check)
        assert "Mutation score (added lines)" not in md
        assert report["mutation_score"] == -1

    def test_mutation_score_section_shown_without_merge_confidence(self):
        # A measured mutation score alone renders the Merge Confidence section.
        check = {**_C_ALLOW, "mutation_score": 0.9}
        _, _, md, _ = _run(_D_HUMAN, _A_CLEAN, _S_NEUTRAL, check)
        assert "Merge Confidence" in md
        assert "90%" in md

    def test_mutation_score_never_changes_result(self):
        check = {**_C_ALLOW, "mutation_score": 0.1}
        result, _, _, _ = _run(_D_HUMAN, _A_CLEAN, _S_NEUTRAL, check)
        assert result == "pass"


# ── Pipeline integrity (stage failures are never a silent pass) ─────────────────

# Stage outputs the action writes when a stage fails to produce a usable result.
_A_INCONCLUSIVE = {"_ods_stage_error": True, "issues": [], "total_lines": 0,
                   "summary": "Analysis inconclusive (ods analyze exited 1)"}
_S_INCONCLUSIVE = {"_ods_stage_error": True, "technical_debt_delta": 0,
                   "verdict": "neutral", "summary": "Scoring inconclusive (ods score exited 1)"}
_C_INCONCLUSIVE = {"_ods_stage_error": True, "allowed": True, "denials": [],
                   "warnings": [], "summary": "Policy check inconclusive (ods check exited 1)"}
_D_DETECT_ERR = {"_ods_detect_error": True, "ai_generated": False, "confidence": 0,
                 "evidence": [], "sources": [], "files": [], "summary": "Detection inconclusive"}


def _run_fm(detect, analyze, score, check, failure_mode):
    """_run with ODS_FAILURE_MODE set for the duration of the call."""
    prev = os.environ.get("ODS_FAILURE_MODE")
    os.environ["ODS_FAILURE_MODE"] = failure_mode
    try:
        return _run(detect, analyze, score, check)
    finally:
        if prev is None:
            os.environ.pop("ODS_FAILURE_MODE", None)
        else:
            os.environ["ODS_FAILURE_MODE"] = prev


class TestPipelineIntegrity:
    def test_all_stages_completed_is_ok(self):
        result, report, md, gh = _run(_D_HUMAN, _A_CLEAN, _S_NEUTRAL, _C_ALLOW)
        assert report["pipeline"]["integrity"] == "ok"
        assert report["pipeline"]["stages"] == {
            "detect": "completed", "analyze": "completed",
            "score": "completed", "check": "completed",
        }
        assert "Pipeline Integrity" not in md
        assert "pipeline_integrity=ok" in gh
        assert result == "pass"

    def test_analyze_failure_is_not_a_silent_pass(self):
        # The old behavior wrote a clean {"issues":[]} and PASSed. It must WARN now.
        result, report, md, _ = _run(_D_HUMAN, _A_INCONCLUSIVE, _S_NEUTRAL, _C_ALLOW)
        assert result == "warn"
        assert report["pipeline"]["integrity"] == "inconclusive"
        assert "analyze" in report["pipeline"]["inconclusive"]
        assert "Pipeline Integrity" in md

    def test_score_failure_warns(self):
        result, report, _, _ = _run(_D_HUMAN, _A_CLEAN, _S_INCONCLUSIVE, _C_ALLOW)
        assert result == "warn"
        assert report["pipeline"]["inconclusive"] == ["score"]

    def test_check_failure_is_not_a_silent_pass(self):
        # A crashed gate defaults allowed=True; it must not read as a clean pass.
        result, report, _, _ = _run(_D_HUMAN, _A_CLEAN, _S_NEUTRAL, _C_INCONCLUSIVE)
        assert result == "warn"
        assert "check" in report["pipeline"]["inconclusive"]

    def test_detect_failure_included_in_pipeline(self):
        result, report, _, _ = _run(_D_DETECT_ERR, _A_CLEAN, _S_NEUTRAL, _C_ALLOW)
        assert result == "warn"
        assert report["pipeline"]["stages"]["detect"] == "inconclusive"

    def test_failure_mode_block_fails_the_run(self):
        result, report, md, _ = _run_fm(_D_HUMAN, _A_INCONCLUSIVE, _S_NEUTRAL, _C_ALLOW, "block")
        assert result == "block"
        assert report["pipeline"]["failure_mode"] == "block"
        assert "block" in md.lower()

    def test_failure_mode_default_is_warn(self):
        result, report, _, _ = _run(_D_HUMAN, _A_INCONCLUSIVE, _S_NEUTRAL, _C_ALLOW)
        assert result == "warn"
        assert report["pipeline"]["failure_mode"] == "warn"

    def test_real_block_still_blocks_regardless_of_pipeline(self):
        deny = {"allowed": False, "denials": ["nope"], "warnings": []}
        result, _, _, _ = _run(_D_HUMAN, _A_CLEAN, _S_NEUTRAL, deny)
        assert result == "block"

    def test_invalid_failure_mode_falls_back_to_warn(self):
        result, report, _, _ = _run_fm(_D_HUMAN, _A_INCONCLUSIVE, _S_NEUTRAL, _C_ALLOW, "nonsense")
        assert result == "warn"
        assert report["pipeline"]["failure_mode"] == "warn"
