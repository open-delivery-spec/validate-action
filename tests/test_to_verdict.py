"""Tests for scripts/to-verdict.py — the AI-review normalizer."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "to_verdict",
    Path(__file__).parent.parent / "scripts" / "to-verdict.py",
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
