"""Tests for scripts/render-attribution.py"""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "render_attribution",
    Path(__file__).parent.parent / "scripts" / "render-attribution.py",
)
ra = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ra)


_SAMPLE = {
    "since": "90 days ago",
    "total_commits": 64,
    "ai_commits": 5,
    "human_commits": 59,
    "ai_commit_share": 0.078125,
    "total_changed_lines": 30056,
    "ai_changed_lines": 1697,
    "ai_line_share": 0.05646,
    "by_tool": {"Claude": 3, "Claude Sonnet 4.6": 2},
}


class TestBuildAttributionMd:
    def test_header_includes_window(self):
        out = ra.build_attribution_md(_SAMPLE)
        assert "AI Attribution" in out
        assert "90 days ago" in out

    def test_commit_and_line_shares_rounded(self):
        out = ra.build_attribution_md(_SAMPLE)
        assert "64 total" in out
        assert "5 AI-assisted (8%)" in out
        assert "1697 AI-assisted (6%)" in out

    def test_by_tool_sorted_desc(self):
        out = ra.build_attribution_md(_SAMPLE)
        # Claude (3) must appear before Claude Sonnet 4.6 (2)
        assert out.index("Claude (3)") < out.index("Claude Sonnet 4.6 (2)")

    def test_non_forensic_caveat_present(self):
        out = ra.build_attribution_md(_SAMPLE)
        assert "not forensic detection" in out

    def test_empty_window(self):
        out = ra.build_attribution_md({"since": "7 days ago", "total_commits": 0})
        assert "No commits in the selected window" in out
        assert "7 days ago" in out

    def test_no_tools_section_when_absent(self):
        r = dict(_SAMPLE)
        r["by_tool"] = {}
        out = ra.build_attribution_md(r)
        assert "By tool" not in out

    def test_missing_keys_do_not_crash(self):
        # Minimal dict with only total_commits should still render.
        out = ra.build_attribution_md({"total_commits": 1})
        assert "AI Attribution" in out
