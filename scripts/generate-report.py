#!/usr/bin/env python3
"""ODS report generator — aggregates detect/analyze/score/check JSON into reports.

Usage: python3 generate-report.py <report-dir> <github-output-file>

Reads:  <report-dir>/detect.json, analyze.json, score.json, check.json
Writes: <report-dir>/ods-report.json, ods-summary.md, index.html, ods-badge.svg
Appends Markdown to $GITHUB_STEP_SUMMARY if set.
Writes step outputs to github-output-file.
"""

import json
import os
import sys
from datetime import datetime, timezone


def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def main():
    report_dir = sys.argv[1]
    github_output = sys.argv[2] if len(sys.argv) > 2 else ""

    detect = load_json(os.path.join(report_dir, "detect.json"))
    analyze = load_json(os.path.join(report_dir, "analyze.json"))
    score = load_json(os.path.join(report_dir, "score.json"))
    check = load_json(os.path.join(report_dir, "check.json"))

    ai_detected = detect.get("ai_generated", False)
    ai_confidence = detect.get("confidence", 0)
    detect_summary = detect.get("summary", "No AI detection result")
    analyze_summary = analyze.get("summary", "No analysis result")
    tech_debt = score.get("technical_debt_delta", 0)
    verdict = score.get("verdict", "neutral")
    recommendation = score.get("recommendation", "")
    policy_allowed = check.get("allowed", True)
    denials = check.get("denials", [])
    warnings_list = check.get("warnings", [])
    issues = analyze.get("issues", [])
    files = detect.get("files", [])
    evidence = detect.get("evidence", [])
    sources = detect.get("sources", [])

    # Determine overall result
    if not policy_allowed:
        overall = "\u274c BLOCK"
        result_value = "block"
    elif ai_detected and ai_confidence >= 0.8 and len(issues) > 0:
        overall = "\u26a0\ufe0f  WARN"
        result_value = "warn"
    elif ai_detected:
        overall = "\u26a0\ufe0f  WARN"
        result_value = "warn"
    else:
        overall = "\u2705 PASS"
        result_value = "pass"

    # Write GitHub step outputs
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"result={result_value}\n")
            f.write(f"ai_detected={'true' if ai_detected else 'false'}\n")
            f.write(f"ai_confidence={ai_confidence}\n")
            f.write(f"tech_debt_delta={tech_debt}\n")
            f.write(f"policy_allowed={'true' if policy_allowed else 'false'}\n")

    # Combined JSON report
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "result": result_value,
        "ai_detected": ai_detected,
        "ai_confidence": ai_confidence,
        "ai_files": files,
        "detection_sources": sources,
        "detection_evidence": evidence,
        "analysis": {
            "total_issues": len(issues),
            "issues": issues,
            "summary": analyze_summary,
        },
        "score": {
            "technical_debt_delta": tech_debt,
            "verdict": verdict,
            "recommendation": recommendation,
            "breakdown": score.get("breakdown", {}),
        },
        "policy": {
            "allowed": policy_allowed,
            "denials": denials,
            "warnings": warnings_list,
        },
    }

    with open(os.path.join(report_dir, "ods-report.json"), "w") as f:
        json.dump(report, f, indent=2)

    # Markdown summary
    md = build_markdown(
        overall=overall,
        result_value=result_value,
        ai_detected=ai_detected,
        ai_confidence=ai_confidence,
        tech_debt=tech_debt,
        verdict=verdict,
        recommendation=recommendation,
        policy_allowed=policy_allowed,
        evidence=evidence,
        analyze_summary=analyze_summary,
        issues=issues,
        score=score,
        denials=denials,
        warnings_list=warnings_list,
        files=files,
    )

    summary_path = os.path.join(report_dir, "ods-summary.md")
    with open(summary_path, "w") as f:
        f.write(md)

    # Append to GitHub step summary
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if step_summary:
        with open(step_summary, "a") as f:
            f.write(md)

    # SVG badge
    svg = build_svg(result_value, ai_confidence, tech_debt)
    with open(os.path.join(report_dir, "ods-badge.svg"), "w") as f:
        f.write(svg)

    # HTML report
    html = build_html(
        result_value=result_value,
        overall=overall,
        ai_detected=ai_detected,
        ai_confidence=ai_confidence,
        tech_debt=tech_debt,
        verdict=verdict,
        policy_allowed=policy_allowed,
        evidence=evidence,
        analyze_summary=analyze_summary,
        issues=issues,
        score=score,
    )
    with open(os.path.join(report_dir, "index.html"), "w") as f:
        f.write(html)

    print(f"Report generated: {os.path.join(report_dir, 'index.html')}")

    # Set result_value for the caller script
    return result_value


def build_markdown(**kw):
    lines = [
        "<!-- ods-compliance-report -->",
        "## ODS AI Code Quality Report",
        "",
        f"**Result:** {kw['overall']}  ",
        f"**AI Detected:** {'\\U0001f916 Yes' if kw['ai_detected'] else '\\U0001f464 No'} (confidence: {kw['ai_confidence']*100:.0f}%)  ",
        f"**Tech Debt Delta:** {kw['tech_debt']:+.1f} ({kw['verdict']})  ",
        f"**Policy:** {'\\u2705 Allowed' if kw['policy_allowed'] else '\\u274c Blocked'}  ",
        "",
    ]

    # Detection
    lines.append("### \\U0001f50d Detection")
    ev = kw["evidence"]
    if ev:
        lines.extend(["", "| Source | Signal | Confidence |", "|--------|--------|-----------|"])
        for e in ev:
            lines.append(f"| {e.get('source','?')} | {e.get('value','?')} | {e.get('confidence',0)*100:.0f}% |")
    else:
        lines.append("No AI code detected.")

    # Analysis
    lines.extend(["", "### \\U0001f4ca Analysis", f"{kw['analyze_summary']}  "])
    issues = kw["issues"]
    if issues:
        lines.extend(["", "| Rule | File | Severity | Message |", "|------|------|----------|---------|"])
        for i in issues[:10]:
            lines.append(f"| {i.get('rule','?')} | {i.get('file','?')} | {i.get('severity','?')} | {i.get('message','?')} |")
        if len(issues) > 10:
            lines.append(f"| ... | ... | ... | _and {len(issues)-10} more_ |")

    # Score
    lines.extend(["", "### \\U0001f4c8 Score"])
    b = kw["score"].get("breakdown", {})
    lines.extend([
        "| Dimension | Value |",
        "|-----------|-------|",
        f"| AI Code Ratio | {b.get('ai_code_ratio',0)*100:.0f}% |",
        f"| Defect Density | {b.get('defect_density',0):.1f} / KLOC |",
        f"| Critical Issues | {b.get('critical_issues',0)} |",
        f"| Test Coverage | {b.get('test_coverage',0)*100:.0f}% |",
        f"| Duplication Rate | {b.get('duplication_rate',0)*100:.0f}% |",
        "",
        f"**Verdict:** {kw['verdict']} \u2014 {kw['recommendation']}",
    ])

    # Policy
    if kw["denials"]:
        lines.extend(["", "### \\U0001f6ab Policy Denials"])
        for d in kw["denials"]:
            lines.append(f"- \\u274c {d}")
    if kw["warnings_list"]:
        lines.extend(["", "### \\u26a0\\ufe0f  Policy Warnings"])
        for w in kw["warnings_list"]:
            lines.append(f"- \\u26a0\\ufe0f  {w}")

    # Files
    files = kw["files"]
    if files:
        lines.extend(["", "### \\U0001f4c1 AI-Detected Files", ""])
        lines.extend([
            "| File | AI Lines | Total | Confidence |",
            "|------|----------|-------|-----------|",
        ])
        for f in files:
            lines.append(f"| {f.get('path','?')} | {f.get('ai_lines',0)} | {f.get('total_lines',0)} | {f.get('confidence',0)*100:.0f}% |")

    return "\n".join(lines) + "\n"


def build_svg(result_value, ai_confidence, tech_debt):
    colors = {"pass": "#2ea043", "warn": "#d29922", "block": "#cf222e"}
    labels = {"pass": "PASS", "warn": "WARN", "block": "BLOCK"}
    color = colors.get(result_value, "#6e7681")
    label = labels.get(result_value, "UNKNOWN")

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="420" height="20">\n'
        f'  <rect width="60" height="20" fill="#6e7681" rx="3"/>\n'
        f'  <text x="30" y="14" fill="#fff" font-family="sans-serif" font-size="11" text-anchor="middle">ODS</text>\n'
        f'  <rect x="60" width="120" height="20" fill="{color}" rx="3"/>\n'
        f'  <text x="120" y="14" fill="#fff" font-family="sans-serif" font-size="11" text-anchor="middle">{label}</text>\n'
        f'  <rect x="180" width="240" height="20" fill="#30363d" rx="3"/>\n'
        f'  <text x="300" y="14" fill="#c9d1d9" font-family="sans-serif" font-size="10" text-anchor="middle">'
        f'ai:{ai_confidence*100:.0f}% debt:{tech_debt:+.1f}</text>\n'
        f'</svg>'
    )


def build_html(**kw):
    evidence_rows = "".join(
        f"<tr><td>{e.get('source','?')}</td><td>{e.get('value','?')}</td><td>{e.get('confidence',0)*100:.0f}%</td></tr>"
        for e in kw["evidence"]
    )
    issue_rows = "".join(
        f"<tr><td>{i.get('rule','?')}</td><td>{i.get('file','?')}</td><td>{i.get('severity','?')}</td><td>{i.get('message','?')}</td></tr>"
        for i in kw["issues"][:20]
    )
    b = kw["score"].get("breakdown", {})

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>ODS AI Code Quality Report</title>
<style>
  body {{ font-family: -apple-system, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; color: #c9d1d9; background: #0d1117; }}
  h1 {{ color: #f0f6fc; }}
  .result {{ font-size: 1.5em; padding: 10px 20px; border-radius: 6px; display: inline-block; }}
  .pass {{ background: #2ea04320; color: #2ea043; border: 1px solid #2ea043; }}
  .warn {{ background: #d2992220; color: #d29922; border: 1px solid #d29922; }}
  .block {{ background: #cf222e20; color: #cf222e; border: 1px solid #cf222e; }}
  table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
  th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #30363d; }}
  th {{ background: #161b22; color: #f0f6fc; }}
  .section {{ margin: 30px 0; }}
  .section h2 {{ border-bottom: 1px solid #30363d; padding-bottom: 8px; }}
</style></head>
<body>
<h1>ODS AI Code Quality Report</h1>
<div class="result {kw['result_value']}">{kw['overall']}</div>
<div class="section"><h2>Summary</h2>
<p><strong>AI Detected:</strong> {'Yes' if kw['ai_detected'] else 'No'} ({kw['ai_confidence']*100:.0f}% confidence)</p>
<p><strong>Tech Debt Delta:</strong> {kw['tech_debt']:+.1f} ({kw['verdict']})</p>
<p><strong>Policy:</strong> {'Allowed' if kw['policy_allowed'] else 'Blocked'}</p>
</div>
<div class="section"><h2>Detection Evidence</h2>
<table><tr><th>Source</th><th>Signal</th><th>Confidence</th></tr>
{evidence_rows}
</table></div>
<div class="section"><h2>Issues</h2>
{kw['analyze_summary']}<br><br>
<table><tr><th>Rule</th><th>File</th><th>Severity</th><th>Message</th></tr>
{issue_rows}
</table></div>
<div class="section"><h2>Score Breakdown</h2>
<table><tr><th>Dimension</th><th>Value</th></tr>
<tr><td>AI Code Ratio</td><td>{b.get('ai_code_ratio',0)*100:.0f}%</td></tr>
<tr><td>Defect Density</td><td>{b.get('defect_density',0):.1f} / KLOC</td></tr>
<tr><td>Critical Issues</td><td>{b.get('critical_issues',0)}</td></tr>
<tr><td>Test Coverage</td><td>{b.get('test_coverage',0)*100:.0f}%</td></tr>
<tr><td>Duplication Rate</td><td>{b.get('duplication_rate',0)*100:.0f}%</td></tr>
</table></div>
</body></html>"""


if __name__ == "__main__":
    result_value = main()
    # Expose result_value to the caller via env file
    with open(os.path.join(sys.argv[1], ".result"), "w") as f:
        f.write(result_value)
