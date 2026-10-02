"""Tests for scripts/to-verdict.py — the AI-review normalizer."""
import importlib.util
import io
import json
import runpy
import sys
from pathlib import Path

_SCRIPT = Path(__file__).parent.parent / "scripts" / "to-verdict.py"

_spec = importlib.util.spec_from_file_location(
    "to_verdict",
    _SCRIPT,
)
tv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tv)


# ── extract_json: tolerate the ways LLMs wrap JSON ────────────────────────────

class TestExtractJson:
    def test_bare_json(self):
        assert tv.extract_json('{"verdict": "approve"}') == {"verdict": "approve"}

    def test_fenced_json(self):
        text = '```json\n{"verdict": "comment"}\n```'
        assert tv.extract_json(text) == {"verdict": "comment"}

    def test_json_with_surrounding_prose(self):
        text = 'Here is my review:\n{"verdict": "request_changes"}\nHope that helps!'
        assert tv.extract_json(text) == {"verdict": "request_changes"}

    def test_braces_inside_strings_dont_confuse_balance(self):
        text = '{"findings": [{"message": "use {} not new Object()"}]}'
        assert tv.extract_json(text)["findings"][0]["message"] == "use {} not new Object()"

    def test_garbage_returns_empty(self):
        assert tv.extract_json("not json at all") == {}

    def test_fence_on_a_single_line(self):
        assert tv.extract_json('```{"verdict": "approve"}```') == {"verdict": "approve"}

    def test_unterminated_fence(self):
        assert tv.extract_json('```json\n{"verdict": "comment"}') == {"verdict": "comment"}

    def test_escaped_quotes_dont_end_a_string(self):
        text = 'Review: {"findings": [{"message": "say \\"}\\" twice"}]} -- end'
        assert tv.extract_json(text)["findings"][0]["message"] == 'say "}" twice'

    def test_balanced_braces_that_are_not_json_are_skipped(self):
        text = 'Template {placeholder} first, then {"verdict": "approve"}'
        assert tv.extract_json(text) == {"verdict": "approve"}

    def test_truncated_object_returns_empty(self):
        # Output cut off mid-object (token limit): nothing balanced to parse.
        assert tv.extract_json('Here you go: {"verdict": "approve", "findings": [') == {}


# ── normalize: always produce a schema-valid verdict ─────────────────────────

class TestNormalize:
    def test_schema_and_reviewer_forced(self):
        v = tv.normalize({"verdict": "approve"}, "claude-code", "", "")
        assert v["schema"] == "ods.dev/review-verdict/v1"
        assert v["reviewer"] == {"tool": "claude-code"}
        assert v["verdict"] == "approve"

    def test_head_sha_stamped(self):
        v = tv.normalize({"verdict": "comment"}, "claude-code", "", "cafe1234")
        assert v["head_sha"] == "cafe1234"

    def test_invalid_verdict_with_high_finding_becomes_request_changes(self):
        raw = {"verdict": "LGTM ship it", "findings": [{"message": "x", "severity": "high"}]}
        v = tv.normalize(raw, "claude-code", "", "")
        assert v["verdict"] == "request_changes"

    def test_invalid_verdict_without_findings_becomes_comment(self):
        v = tv.normalize({"verdict": "??"}, "claude-code", "", "")
        assert v["verdict"] == "comment"

    def test_never_fabricates_approve(self):
        # A missing/garbage verdict must never resolve to approve.
        v = tv.normalize({"findings": [{"message": "nit"}]}, "claude-code", "", "")
        assert v["verdict"] != "approve"

    def test_findings_coerced_and_junk_dropped(self):
        raw = {
            "verdict": "request_changes",
            "findings": [
                {"message": "real", "file": "a.go", "line": 5, "severity": "high",
                 "category": "correctness", "suggestion": "fix it", "bogus": "drop me"},
                {"file": "b.go"},                       # no message → dropped
                {"message": "  ", "severity": "high"},  # blank message → dropped
                {"message": "bad sev", "severity": "SUPER"},   # invalid enum → sev dropped
                {"message": "bad line", "line": 0},            # line < 1 → line dropped
                {"message": "bool line", "line": True},        # bool → line dropped
            ],
        }
        v = tv.normalize(raw, "claude-code", "", "")
        f = v["findings"]
        # Kept, in order: real, bad-sev, bad-line, bool-line (2 dropped for no message).
        assert len(f) == 4
        assert "bogus" not in f[0] and f[0]["line"] == 5 and f[0]["severity"] == "high"
        assert "severity" not in f[1]  # invalid enum stripped
        assert "line" not in f[2]      # line 0 stripped
        assert "line" not in f[3]      # bool stripped

    def test_no_findings_key_omitted(self):
        v = tv.normalize({"verdict": "approve"}, "claude-code", "", "")
        assert "findings" not in v

    def test_findings_that_are_not_objects_are_dropped(self):
        raw = {"verdict": "comment", "findings": ["looks fine to me", {"message": "real"}]}
        assert tv.normalize(raw, "t", "", "")["findings"] == [{"message": "real"}]

    def test_model_from_flag_and_from_payload(self):
        assert tv.normalize({"verdict": "approve"}, "t", "claude-opus", "")["reviewer"]["model"] == "claude-opus"
        raw = {"verdict": "approve", "reviewer": {"model": "sonnet-4-5"}}
        assert tv.normalize(raw, "t", "", "")["reviewer"]["model"] == "sonnet-4-5"


def test_end_to_end_messy_llm_output():
    """A realistic messy model response normalizes to a valid verdict."""
    text = (
        "Sure! Here's my review:\n\n"
        "```json\n"
        '{"verdict": "request_changes", "findings": ['
        '{"file": "auth.py", "line": 42, "severity": "high", "category": "security",'
        ' "message": "Token compared with local time; skew bypasses expiry."}]}\n'
        "```\n\nLet me know if you want more detail."
    )
    raw = tv.extract_json(text)
    v = tv.normalize(raw, "claude-code", "claude-opus-4-8", "abc123")
    assert v["schema"] == "ods.dev/review-verdict/v1"
    assert v["verdict"] == "request_changes"
    assert v["reviewer"] == {"tool": "claude-code", "model": "claude-opus-4-8"}
    assert v["head_sha"] == "abc123"
    assert v["findings"][0]["file"] == "auth.py"


# ── main: the command line the recipe and the docs use ───────────────────────

class TestMain:
    def test_file_in_verdict_out(self, tmp_path, monkeypatch, capsys):
        raw = tmp_path / "raw.txt"
        raw.write_text('Sure!\n{"verdict": "request_changes",'
                       ' "findings": [{"message": "m", "severity": "high"}]}\n')
        out = tmp_path / "verdict.json"
        monkeypatch.setattr(sys, "argv", [
            "to-verdict.py", str(raw), "--tool", "codex", "--model", "gpt-x",
            "--head-sha", "abc123", "--out", str(out),
        ])
        tv.main()
        assert json.loads(out.read_text()) == {
            "schema": "ods.dev/review-verdict/v1",
            "reviewer": {"tool": "codex", "model": "gpt-x"},
            "verdict": "request_changes",
            "head_sha": "abc123",
            "findings": [{"message": "m", "severity": "high"}],
        }
        captured = capsys.readouterr()
        assert captured.out == ""
        assert f"Wrote request_changes verdict (1 finding(s)) to {out}" in captured.err

    def test_stdin_in_stdout_out(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["to-verdict.py"])
        monkeypatch.setattr(sys, "stdin", io.StringIO('{"verdict": "approve"}'))
        monkeypatch.delenv("ODS_HEAD_SHA", raising=False)
        monkeypatch.delenv("GITHUB_SHA", raising=False)
        tv.main()
        assert json.loads(capsys.readouterr().out) == {
            "schema": "ods.dev/review-verdict/v1",
            "reviewer": {"tool": "claude-code"},
            "verdict": "approve",
        }

    def test_head_sha_defaults_to_ods_head_sha_then_github_sha(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["to-verdict.py"])
        monkeypatch.setenv("GITHUB_SHA", "merge-sha")
        monkeypatch.setenv("ODS_HEAD_SHA", "head-sha")
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
        tv.main()
        assert json.loads(capsys.readouterr().out)["head_sha"] == "head-sha"

        monkeypatch.delenv("ODS_HEAD_SHA")
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
        tv.main()
        assert json.loads(capsys.readouterr().out)["head_sha"] == "merge-sha"

    def test_runs_as_a_script(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["to-verdict.py", "--head-sha", ""])
        monkeypatch.setattr(sys, "stdin", io.StringIO("no verdict here"))
        runpy.run_path(str(_SCRIPT), run_name="__main__")
        # Nothing parseable: a safe, schema-valid "comment", never "approve".
        assert json.loads(capsys.readouterr().out)["verdict"] == "comment"
