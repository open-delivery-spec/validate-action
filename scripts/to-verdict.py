#!/usr/bin/env python3
"""Normalize an AI reviewer's output into an ODS review-verdict/v1 document.

LLMs emit *best-effort* JSON — wrapped in prose, in ```json fences, with stray
keys or an out-of-enum verdict. This adapter is the thin, tolerant layer that
turns that into a schema-valid verdict the deterministic gate can safely
consume. Bring your own model and key; ODS just normalizes and enforces.

Usage:
    your-llm-review > raw.txt
    python3 to-verdict.py raw.txt --tool claude-code --out verdict.json
    # or pipe:
    your-llm-review | python3 to-verdict.py --tool claude-code > verdict.json

Then feed the file to the gate:
    ods check --ai-review verdict.json          # (CLI)
    # or the action's `ai-review:` input.

Schema: https://open-delivery-spec.dev/schemas/review-verdict/v1.json
"""

import argparse
import json
import os
import sys

SCHEMA = "ods.dev/review-verdict/v1"
VERDICTS = ("approve", "request_changes", "comment")
SEVERITIES = ("info", "low", "medium", "high", "critical")


def extract_json(text):
    """Pull the first balanced JSON object out of arbitrary model output.

    Tolerates ```json fences and surrounding prose. Returns {} if none parses.
    """
    text = text.strip()
    # Strip a leading ```json / ``` fence if the whole thing is fenced.
    if text.startswith("```"):
        first_nl = text.find("\n")
        if first_nl != -1:
            text = text[first_nl + 1 :]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    text = text.strip()
    # Fast path: the whole thing is JSON.
    try:
        return json.loads(text)
    except Exception:
        pass
    # Scan for the first balanced {...} and try to parse it.
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            c = text[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except Exception:
                        break
        start = text.find("{", start + 1)
    return {}


def derive_verdict(raw, findings):
    """Pick a safe verdict when the model didn't give a valid one.

    Conservative by design: a high/critical finding routes to request_changes;
    otherwise 'comment' (which never loosens or forces elevation). We never
    fabricate 'approve' — an approve is inert in the gate anyway, and inventing
    one from silence would be the wrong default.
    """
    v = str(raw.get("verdict", "")).strip().lower()
    if v in VERDICTS:
        return v
    for f in findings:
        if f.get("severity") in ("high", "critical"):
            return "request_changes"
    return "comment"


def normalize_findings(raw):
    out = []
    for f in raw.get("findings", []) or []:
        if not isinstance(f, dict):
            continue
        msg = f.get("message")
        if not isinstance(msg, str) or not msg.strip():
            continue  # message is the only required field
        item = {"message": msg.strip()}
        if isinstance(f.get("file"), str) and f["file"].strip():
            item["file"] = f["file"].strip()
        line = f.get("line")
        if isinstance(line, bool):
            line = None  # bool is an int subclass — reject it
        if isinstance(line, int) and line >= 1:
            item["line"] = line
        sev = str(f.get("severity", "")).strip().lower()
        if sev in SEVERITIES:
            item["severity"] = sev
        if isinstance(f.get("category"), str) and f["category"].strip():
            item["category"] = f["category"].strip()
        if isinstance(f.get("suggestion"), str) and f["suggestion"].strip():
            item["suggestion"] = f["suggestion"].strip()
        out.append(item)
    return out


def normalize(raw, tool, model, head_sha):
    findings = normalize_findings(raw)
    verdict = {
        "schema": SCHEMA,
        "reviewer": {"tool": tool},
        "verdict": derive_verdict(raw, findings),
    }
    # Model may come from the flag or from what the LLM reported about itself.
    model = model or (raw.get("reviewer") or {}).get("model") or raw.get("model")
    if isinstance(model, str) and model.strip():
        verdict["reviewer"]["model"] = model.strip()
    head_sha = head_sha or raw.get("head_sha")
    if isinstance(head_sha, str) and head_sha.strip():
        verdict["head_sha"] = head_sha.strip()
    if findings:
        verdict["findings"] = findings
    return verdict


def main():
    ap = argparse.ArgumentParser(description="Normalize LLM output into review-verdict/v1.")
    ap.add_argument("input", nargs="?", help="File with the model's output (default: stdin)")
    ap.add_argument("--tool", default="claude-code", help="Reviewer tool name")
    ap.add_argument("--model", default="", help="Model identifier (optional)")
    ap.add_argument(
        "--head-sha",
        default=os.environ.get("ODS_HEAD_SHA") or os.environ.get("GITHUB_SHA", ""),
        help="Commit the review applies to (defaults to ODS_HEAD_SHA / GITHUB_SHA)",
    )
    ap.add_argument("--out", help="Write here (default: stdout)")
    args = ap.parse_args()

    text = open(args.input).read() if args.input else sys.stdin.read()
    raw = extract_json(text)
    verdict = normalize(raw, args.tool, args.model, args.head_sha)

    doc = json.dumps(verdict, indent=2) + "\n"
    if args.out:
        with open(args.out, "w") as f:
            f.write(doc)
        print(f"Wrote {verdict['verdict']} verdict ({len(verdict.get('findings', []))} finding(s)) to {args.out}",
              file=sys.stderr)
    else:
        sys.stdout.write(doc)


if __name__ == "__main__":
    main()
