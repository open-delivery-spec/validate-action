#!/usr/bin/env python3
"""Render `ods report --json` output into a Markdown attribution section.

Usage: python3 render-attribution.py <attribution.json>
Prints the Markdown to stdout.
"""

import json
import sys


def build_attribution_md(r):
    """Build the Markdown attribution section from an ods report dict."""
    since = r.get("since", "recent history")
    total = r.get("total_commits", 0)

    header = f"## \U0001f4ca AI Attribution — {since}"
    if not total:
        return f"{header}\n\nNo commits in the selected window."

    ai = r.get("ai_commits", 0)
    human = r.get("human_commits", 0)
    commit_share = r.get("ai_commit_share", 0) * 100
    total_lines = r.get("total_changed_lines", 0)
    ai_lines = r.get("ai_changed_lines", 0)
    line_share = r.get("ai_line_share", 0) * 100

    lines = [
        header,
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Commits | {total} total · {ai} AI-assisted ({commit_share:.0f}%) · {human} human |",
        f"| Changed lines | {total_lines} total · {ai_lines} AI-assisted ({line_share:.0f}%) |",
    ]

    by_tool = r.get("by_tool") or {}
    if by_tool:
        ordered = sorted(by_tool.items(), key=lambda kv: (-kv[1], kv[0]))
        tools = ", ".join(f"{tool} ({count})" for tool, count in ordered)
        lines += ["", f"**By tool:** {tools}"]

    lines += [
        "",
        "_Attribution from `Co-Authored-By` trailers — what AI tools disclose, "
        "not forensic detection._",
    ]
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: render-attribution.py <attribution.json>")
    with open(sys.argv[1]) as f:
        report = json.load(f)
    print(build_attribution_md(report))


if __name__ == "__main__":
    main()
