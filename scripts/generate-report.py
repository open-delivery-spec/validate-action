#!/usr/bin/env python3
"""ODS report generator — aggregates detect/analyze/score/check JSON into reports.

Usage: python3 generate-report.py <report-dir> <github-output-file>

Reads:  <report-dir>/detect.json, analyze.json, score.json, check.json
Writes: <report-dir>/ods-report.json, ods-summary.md, index.html, ods-badge.svg
Appends Markdown to $GITHUB_STEP_SUMMARY if set.
Writes step outputs to github-output-file.
"""

import glob
import html
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


def md_cell(value):
    """Sanitize a value for safe rendering inside a Markdown table cell.

    Escapes pipes (which would break the column layout) and collapses
    newlines, so arbitrary PR/branch/issue text can never corrupt the table.
    """
    text = str(value)
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def h(value):
    """HTML-escape a value (including quotes) for safe interpolation."""
    return html.escape(str(value), quote=True)


def coverage_label(cov):
    """Format a coverage fraction for display.

    ODS uses -1.0 as the "not measured" sentinel; rendering it as a percentage
    produces a nonsensical "-100%". Show "N/A" instead, matching the CLI's
    FormatScore behavior.
    """
    try:
        cov = float(cov)
    except (TypeError, ValueError):
        return "N/A"
    if cov < 0:
        return "N/A"
    return f"{cov*100:.0f}%"


def issue_severity_counts(issues):
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for issue in issues:
        sev = str(issue.get("severity", "")).lower()
        if sev in counts:
            counts[sev] += 1
    return counts


def build_risk_brief(
    *,
    policy_allowed,
    detect_error,
    ai_detected,
    ai_confidence,
    review_tier,
    tech_debt,
    verdict,
    denials,
    warnings_list,
    issues,
    score_breakdown,
):
    counts = issue_severity_counts(issues)
    reasons = []

    if detect_error:
        reasons.append("AI detection inconclusive; confidence in attribution is reduced")
    if denials:
        reasons.append(f"Policy denied merge ({len(denials)} denial(s))")
    if counts["critical"] > 0:
        reasons.append(f"{counts['critical']} critical issue(s) detected")
    if counts["high"] > 0:
        reasons.append(f"{counts['high']} high-severity issue(s) detected")
    if tech_debt >= 5.0:
        reasons.append(f"Technical debt delta is {tech_debt:+.1f} (block range)")
    elif tech_debt >= 3.0:
        reasons.append(f"Technical debt delta is {tech_debt:+.1f} (high-risk range)")
    if ai_detected and ai_confidence >= 0.8:
        reasons.append(f"High-confidence AI involvement ({ai_confidence*100:.0f}%)")

    coverage = score_breakdown.get("test_coverage")
    try:
        coverage = float(coverage)
    except (TypeError, ValueError):
        coverage = -1
    if 0 <= coverage < 0.3:
        reasons.append(f"Low measured test coverage ({coverage*100:.0f}%)")

    if not reasons and warnings_list:
        reasons.append(f"{len(warnings_list)} policy warning(s) require reviewer attention")
    if not reasons and verdict == "increase":
        reasons.append("Score verdict is increase; this PR needs careful review")
    if not reasons:
        reasons.append("No strong risk signals detected")

    if not policy_allowed:
        level = "high"
        action = "Block merge. Fix denials, then require elevated human review."
    elif detect_error or review_tier == "elevated" or counts["critical"] > 0 or counts["high"] > 0 or tech_debt >= 3.0:
        level = "high"
        action = "Require elevated human review focused on flagged files and rules."
    elif ai_detected or len(issues) > 0 or verdict == "increase" or warnings_list:
        level = "medium"
        action = "Run standard human review; verify tests and high-impact logic paths."
    else:
        level = "low"
        action = "Low review risk. Proceed with normal approval flow."

    return {
        "level": level,
        "review_tier": review_tier,
        "recommended_action": action,
        "reasons": reasons[:4],
        "stats": {
            "critical_issues": counts["critical"],
            "high_issues": counts["high"],
            "medium_issues": counts["medium"],
            "ai_confidence": ai_confidence,
            "technical_debt_delta": tech_debt,
        },
    }


def main():
    report_dir = sys.argv[1]
    github_output = sys.argv[2] if len(sys.argv) > 2 else ""

    detect = load_json(os.path.join(report_dir, "detect.json"))
    analyze = load_json(os.path.join(report_dir, "analyze.json"))
    score = load_json(os.path.join(report_dir, "score.json"))
    check = load_json(os.path.join(report_dir, "check.json"))

    # AI reviewer verdicts (review-verdict/v1) copied in by the action when
    # the ai-review input is set. Best effort: unparseable files are skipped.
    ai_reviews = []
    for path in sorted(glob.glob(os.path.join(report_dir, "ai-review-*.json"))):
        verdict = load_json(path)
        if verdict.get("verdict"):
            ai_reviews.append(verdict)

    detect_error = detect.get("_ods_detect_error", False)
    ai_detected = detect.get("ai_generated", False)
    ai_confidence = detect.get("confidence", 0)
    detect_summary = detect.get("summary", "No AI detection result")
    analyze_summary = analyze.get("summary", "No analysis result")
    tech_debt = score.get("technical_debt_delta", 0)
    verdict = score.get("verdict", "neutral")
    recommendation = score.get("recommendation", "")
    policy_allowed = check.get("allowed", True)
    # Absent on policies (or CLIs) without review routing — treat as standard.
    review_tier = check.get("review_tier") or "standard"
    denials = check.get("denials", [])
    warnings_list = check.get("warnings", [])
    issues = analyze.get("issues", [])
    files = detect.get("files", [])
    evidence = detect.get("evidence", [])
    sources = detect.get("sources", [])
    score_breakdown = score.get("breakdown", {})
    risk_brief = build_risk_brief(
        policy_allowed=policy_allowed,
        detect_error=detect_error,
        ai_detected=ai_detected,
        ai_confidence=ai_confidence,
        review_tier=review_tier,
        tech_debt=tech_debt,
        verdict=verdict,
        denials=denials,
        warnings_list=warnings_list,
        issues=issues,
        score_breakdown=score_breakdown,
    )

    # Determine gate result (merge gate status only).
    # Risk level is handled independently by Risk Brief.
    if not policy_allowed:
        overall = "\u274c BLOCK"
        result_value = "block"
    elif detect_error:
        # Detection failed \u2014 treat as warn so the PR isn't silently passed
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
            f.write(f"review_tier={review_tier}\n")
            f.write(f"detect_error={'true' if detect_error else 'false'}\n")

    # Combined JSON report
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "result": result_value,
        "detect_error": detect_error,
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
            "breakdown": score_breakdown,
        },
        "policy": {
            "allowed": policy_allowed,
            "review_tier": review_tier,
            "denials": denials,
            "warnings": warnings_list,
        },
        "risk_brief": risk_brief,
        "ai_reviews": ai_reviews,
    }

    with open(os.path.join(report_dir, "ods-report.json"), "w") as f:
        json.dump(report, f, indent=2)

    # Markdown summary
    md = build_markdown(
        overall=overall,
        result_value=result_value,
        detect_error=detect_error,
        ai_detected=ai_detected,
        ai_confidence=ai_confidence,
        tech_debt=tech_debt,
        verdict=verdict,
        recommendation=recommendation,
        policy_allowed=policy_allowed,
        review_tier=review_tier,
        evidence=evidence,
        analyze_summary=analyze_summary,
        issues=issues,
        score=score,
        denials=denials,
        warnings_list=warnings_list,
        files=files,
        risk_brief=risk_brief,
        ai_reviews=ai_reviews,
    )

    summary_path = os.path.join(report_dir, "ods-summary.md")
    with open(summary_path, "w") as f:
        f.write(md)

    # Append to GitHub step summary (respect INPUT_SUMMARY env var)
    if os.environ.get("INPUT_SUMMARY", "true").lower() == "true":
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
        detect_error=detect_error,
        ai_detected=ai_detected,
        ai_confidence=ai_confidence,
        tech_debt=tech_debt,
        verdict=verdict,
        policy_allowed=policy_allowed,
        evidence=evidence,
        analyze_summary=analyze_summary,
        issues=issues,
        score=score,
        risk_brief=risk_brief,
    )
    with open(os.path.join(report_dir, "index.html"), "w") as f:
        f.write(html)

    print(f"Report generated: {os.path.join(report_dir, 'index.html')}")

    # Set result_value for the caller script
    return result_value


def build_markdown(**kw):
    # NOTE: keep backslash escapes out of f-string expression braces \u2014 that
    # syntax requires Python 3.12+, but CI runners may ship an older python3.
    if kw.get("detect_error"):
        ai_label = "⚠️ Inconclusive"
    elif kw["ai_detected"]:
        ai_label = "\U0001f916 Yes"
    else:
        ai_label = "\U0001f464 No"
    policy_label = "\u2705 Allowed" if kw["policy_allowed"] else "\u274c Blocked"
    lines = [
        "<!-- ods-compliance-report -->",
        "## ODS AI Code Quality Report",
        "",
        f"**Gate Result:** {kw['overall']}  ",
        f"**AI Detected:** {ai_label} (confidence: {kw['ai_confidence']*100:.0f}%)  ",
        f"**Tech Debt Delta:** {kw['tech_debt']:+.1f} ({kw['verdict']})  ",
        f"**Policy:** {policy_label}  ",
    ]
    if kw["policy_allowed"]:
        tier = kw.get("review_tier", "standard")
        tier_icon = {"auto": "\U0001f7e2", "standard": "\U0001f535", "elevated": "\U0001f7e0"}.get(tier, "")
        lines.append(f"**Review Tier:** {tier_icon} {tier}  ")
    lines.append("")
    risk = kw.get("risk_brief", {})
    risk_level = str(risk.get("level", "medium")).lower()
    risk_icon = {"high": "🔴", "medium": "🟠", "low": "🟢"}.get(risk_level, "🟠")
    lines.extend([
        "### 🧭 Risk Brief",
        "",
        f"**Risk Level:** {risk_icon} {risk_level}  ",
        f"**Review Action:** {risk.get('recommended_action', 'Standard review recommended')}  ",
    ])
    reasons = risk.get("reasons", [])
    if reasons:
        lines.append("")
        lines.append("**Why this level:**")
        for reason in reasons:
            lines.append(f"- {reason}")
    lines.append("")

    # Detection
    lines.append("### \U0001f50d Detection")
    if kw.get("detect_error"):
        lines.extend([
            "",
            "> **⚠️ Detection inconclusive** — `ods detect` did not complete successfully.",
            "> This PR is marked **WARN** until detection can be confirmed.",
            "> Check the workflow logs (`ods detect error output` group) for the root cause.",
            "",
        ])
    ev = kw["evidence"]
    if ev:
        lines.extend(["", "| Source | Signal | Confidence |", "|--------|--------|-----------|"])
        for e in ev:
            lines.append(f"| {md_cell(e.get('source','?'))} | {md_cell(e.get('value','?'))} | {e.get('confidence',0)*100:.0f}% |")
    elif not kw.get("detect_error"):
        lines.append("No AI code detected.")

    # Analysis
    lines.extend(["", "### \U0001f4ca Analysis", f"{kw['analyze_summary']}  "])
    issues = kw["issues"]
    if issues:
        lines.extend(["", "| Rule | File | Severity | Message |", "|------|------|----------|---------|"])
        for i in issues[:10]:
            lines.append(f"| {md_cell(i.get('rule','?'))} | {md_cell(i.get('file','?'))} | {md_cell(i.get('severity','?'))} | {md_cell(i.get('message','?'))} |")
        if len(issues) > 10:
            lines.append(f"| ... | ... | ... | _and {len(issues)-10} more_ |")

    # Score
    lines.extend(["", "### \U0001f4c8 Score"])
    b = kw["score"].get("breakdown", {})
    lines.extend([
        "| Dimension | Value |",
        "|-----------|-------|",
        f"| AI Code Ratio | {b.get('ai_code_ratio',0)*100:.0f}% |",
        f"| Defect Density | {b.get('defect_density',0):.1f} / KLOC |",
        f"| Critical Issues | {b.get('critical_issues',0)} |",
        f"| Test Coverage | {coverage_label(b.get('test_coverage',0))} |",
        f"| Duplication Rate | {b.get('duplication_rate',0)*100:.0f}% |",
        "",
        f"**Verdict:** {kw['verdict']} \u2014 {kw['recommendation']}",
    ])

    # AI Review — semantic verdicts from AI reviewers. Advisory by default:
    # they route review attention and never block unless the policy opts in.
    ai_reviews = kw.get("ai_reviews") or []
    if ai_reviews:
        verdict_icon = {
            "approve": "✅",
            "request_changes": "\U0001f536",
            "comment": "\U0001f4ac",
        }
        lines.extend([
            "",
            "### \U0001f9e0 AI Review",
            "",
            "| Reviewer | Verdict | Findings |",
            "|----------|---------|----------|",
        ])
        for r in ai_reviews:
            reviewer = r.get("reviewer") or {}
            name = reviewer.get("tool", "?")
            if reviewer.get("model"):
                name = f"{name} ({reviewer['model']})"
            v = r.get("verdict", "?")
            icon = verdict_icon.get(v, "")
            lines.append(f"| {md_cell(name)} | {icon} {md_cell(v)} | {len(r.get('findings') or [])} |")
        findings = [
            (r.get("reviewer", {}).get("tool", "?"), f)
            for r in ai_reviews
            for f in (r.get("findings") or [])
        ]
        if findings:
            lines.extend([
                "",
                "| Reviewer | Location | Severity | Message |",
                "|----------|----------|----------|---------|",
            ])
            for tool, f in findings[:10]:
                loc = f.get("file", "?")
                if f.get("line"):
                    loc = f"{loc}:{f['line']}"
                lines.append(f"| {md_cell(tool)} | {md_cell(loc)} | {md_cell(f.get('severity', '—'))} | {md_cell(f.get('message', '?'))} |")
            if len(findings) > 10:
                lines.append(f"| ... | ... | ... | _and {len(findings)-10} more_ |")
        lines.extend([
            "",
            "_AI review verdicts are advisory: they can route extra human review, never block, unless your policy opts in._",
        ])

    # Policy
    if kw["denials"]:
        lines.extend(["", "### \U0001f6ab Policy Denials"])
        for d in kw["denials"]:
            lines.append(f"- \u274c {d}")
    if kw["warnings_list"]:
        lines.extend(["", "### \u26a0\ufe0f  Policy Warnings"])
        for w in kw["warnings_list"]:
            lines.append(f"- \u26a0\ufe0f  {w}")

    # Files
    files = kw["files"]
    if files:
        lines.extend(["", "### \U0001f4c1 AI-Detected Files", ""])
        lines.extend([
            "| File | AI Lines | Total | Confidence |",
            "|------|----------|-------|-----------|",
        ])
        for f in files:
            lines.append(f"| {md_cell(f.get('path','?'))} | {f.get('ai_lines',0)} | {f.get('total_lines',0)} | {f.get('confidence',0)*100:.0f}% |")

    return "\n".join(lines) + "\n"


def build_svg(result_value, ai_confidence, tech_debt):
    colors = {"pass": "#2ea043", "warn": "#d29922", "block": "#cf222e"}
    labels = {"pass": "PASS", "warn": "WARN", "block": "BLOCK"}
    color = colors.get(result_value, "#6e7681")
    label = labels.get(result_value, "UNKNOWN")

    # Flat shields.io-style badge: [ ODS ][ STATUS ][ ai:NN% · debt:±N.N ]
    meta = f"ai {ai_confidence*100:.0f}% · debt {tech_debt:+.1f}"
    label_w, status_w, meta_w = 44, 70, 150
    total = label_w + status_w + meta_w

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total}" height="20" '
        f'role="img" aria-label="ODS: {label} ({h(meta)})">\n'
        f'  <linearGradient id="s" x2="0" y2="100%">\n'
        f'    <stop offset="0" stop-color="#fff" stop-opacity=".1"/>\n'
        f'    <stop offset="1" stop-opacity=".1"/>\n'
        f'  </linearGradient>\n'
        f'  <clipPath id="r"><rect width="{total}" height="20" rx="3" fill="#fff"/></clipPath>\n'
        f'  <g clip-path="url(#r)">\n'
        f'    <rect width="{label_w}" height="20" fill="#24292f"/>\n'
        f'    <rect x="{label_w}" width="{status_w}" height="20" fill="{color}"/>\n'
        f'    <rect x="{label_w+status_w}" width="{meta_w}" height="20" fill="#30363d"/>\n'
        f'    <rect width="{total}" height="20" fill="url(#s)"/>\n'
        f'  </g>\n'
        f'  <g fill="#fff" text-anchor="middle" '
        f'font-family="Segoe UI,Helvetica,Arial,sans-serif" font-size="11">\n'
        f'    <text x="{label_w/2:.0f}" y="14" font-weight="bold">ODS</text>\n'
        f'    <text x="{label_w+status_w/2:.0f}" y="14" font-weight="bold">{label}</text>\n'
        f'    <text x="{label_w+status_w+meta_w/2:.0f}" y="14" fill="#c9d1d9">{h(meta)}</text>\n'
        f'  </g>\n'
        f'</svg>'
    )


def build_html(**kw):
    sev_badge = (
        lambda s: f'<span class="sev sev-{h(str(s).lower())}">{h(s)}</span>'
    )
    if kw.get("detect_error"):
        _detect_empty = (
            '<tr><td colspan="3" class="empty detect-error">'
            '⚠️ Detection inconclusive — ods detect did not complete. '
            'Check workflow logs for the root cause.</td></tr>'
        )
    else:
        _detect_empty = '<tr><td colspan="3" class="empty">No AI code detected.</td></tr>'
    evidence_rows = "".join(
        f"<tr><td>{h(e.get('source','?'))}</td><td>{h(e.get('value','?'))}</td>"
        f"<td class=num>{e.get('confidence',0)*100:.0f}%</td></tr>"
        for e in kw["evidence"]
    ) or _detect_empty
    issue_rows = "".join(
        f"<tr><td><code>{h(i.get('rule','?'))}</code></td><td>{h(i.get('file','?'))}</td>"
        f"<td>{sev_badge(i.get('severity','?'))}</td><td>{h(i.get('message','?'))}</td></tr>"
        for i in kw["issues"][:20]
    ) or '<tr><td colspan="4" class="empty">No quality issues detected.</td></tr>'
    b = kw["score"].get("breakdown", {})
    risk = kw.get("risk_brief", {})
    risk_level = str(risk.get("level", "medium")).lower()
    risk_badge = {"high": "🔴 HIGH", "medium": "🟠 MEDIUM", "low": "🟢 LOW"}.get(risk_level, "🟠 MEDIUM")
    risk_reasons = "".join(f"<li>{h(r)}</li>" for r in (risk.get("reasons") or []))
    result_value = kw["result_value"]
    overall_text = {"pass": "✅ PASS", "warn": "⚠️ WARN", "block": "❌ BLOCK"}.get(
        result_value, h(kw["overall"])
    )
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    def bar(label, pct, display=None):
        shown = display if display is not None else f"{pct:.0f}%"
        return (
            f'<div class="metric"><div class="metric-head"><span>{h(label)}</span>'
            f'<span class="num">{h(shown)}</span></div>'
            f'<div class="track"><div class="fill" style="width:{min(max(pct,0),100):.0f}%"></div></div></div>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ODS AI Code Quality Report</title>
<style>
  :root {{ --bg:#0d1117; --panel:#161b22; --border:#30363d; --fg:#c9d1d9; --muted:#8b949e; --fg-strong:#f0f6fc;
           --pass:#2ea043; --warn:#d29922; --block:#cf222e; --accent:#58a6ff; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
          max-width: 880px; margin: 0 auto; padding: 40px 20px; color: var(--fg); background: var(--bg);
          line-height: 1.55; }}
  a {{ color: var(--accent); }}
  header {{ display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px;
            border-bottom: 1px solid var(--border); padding-bottom: 16px; margin-bottom: 8px; }}
  header h1 {{ font-size: 1.4em; color: var(--fg-strong); margin: 0; }}
  header .sub {{ color: var(--muted); font-size: .85em; }}
  .result {{ font-size: 1.25em; font-weight: 600; padding: 8px 18px; border-radius: 999px; display: inline-block; }}
  .pass {{ background: #2ea04318; color: var(--pass); border: 1px solid var(--pass); }}
  .warn {{ background: #d2992218; color: var(--warn); border: 1px solid var(--warn); }}
  .block {{ background: #cf222e18; color: var(--block); border: 1px solid var(--block); }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 24px 0; }}
  .card {{ background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 14px 16px; }}
  .card .label {{ color: var(--muted); font-size: .8em; text-transform: uppercase; letter-spacing: .04em; }}
  .card .value {{ font-size: 1.35em; font-weight: 600; color: var(--fg-strong); margin-top: 4px; }}
  .section {{ margin: 32px 0; }}
  .section h2 {{ font-size: 1.05em; color: var(--fg-strong); border-bottom: 1px solid var(--border);
                 padding-bottom: 8px; margin-bottom: 14px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: .92em; }}
  th, td {{ padding: 9px 12px; text-align: left; border-bottom: 1px solid var(--border); vertical-align: top; }}
  th {{ background: var(--panel); color: var(--fg-strong); font-weight: 600; }}
  td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  td.empty {{ color: var(--muted); text-align: center; padding: 18px; }}
  td.detect-error {{ color: var(--warn); }}
  code {{ background: #6e768133; padding: 1px 6px; border-radius: 4px; font-size: .9em; }}
  .sev {{ font-size: .8em; font-weight: 600; padding: 2px 8px; border-radius: 999px; white-space: nowrap; }}
  .sev-critical {{ background: #cf222e22; color: var(--block); }}
  .sev-high {{ background: #d1242f22; color: #f85149; }}
  .sev-medium {{ background: #d2992222; color: var(--warn); }}
  .sev-low {{ background: #2ea04322; color: var(--pass); }}
  .metric {{ margin: 12px 0; }}
  .metric-head {{ display: flex; justify-content: space-between; font-size: .9em; margin-bottom: 4px; }}
  .track {{ background: var(--panel); border-radius: 999px; height: 8px; overflow: hidden; border: 1px solid var(--border); }}
  .fill {{ background: var(--accent); height: 100%; }}
  footer {{ margin-top: 40px; padding-top: 16px; border-top: 1px solid var(--border); color: var(--muted); font-size: .82em; }}
</style>
</head>
<body>
<header>
  <div>
    <h1>ODS AI Code Quality Report</h1>
    <div class="sub">Detect · Analyze · Score · Enforce</div>
  </div>
  <div class="result {result_value}">{overall_text}</div>
</header>

<div class="cards">
  <div class="card"><div class="label">AI Detected</div>
    <div class="value">{'⚠️ Inconclusive' if kw.get('detect_error') else ('🤖 Yes' if kw['ai_detected'] else '👤 No')}</div>
    <div class="sub">{kw['ai_confidence']*100:.0f}% confidence</div></div>
  <div class="card"><div class="label">Tech Debt Delta</div>
    <div class="value">{kw['tech_debt']:+.1f}</div>
    <div class="sub">{h(kw['verdict'])}</div></div>
  <div class="card"><div class="label">Policy</div>
    <div class="value">{'✅ Allowed' if kw['policy_allowed'] else '❌ Blocked'}</div></div>
  <div class="card"><div class="label">Risk Brief</div>
    <div class="value">{risk_badge}</div>
    <div class="sub">{h(risk.get('recommended_action', 'Standard review recommended'))}</div></div>
</div>

<div class="section"><h2>🧭 Risk Brief</h2>
<ul>{risk_reasons or '<li>No strong risk signals detected.</li>'}</ul>
</div>

<div class="section"><h2>🔍 Detection Evidence</h2>
<table><thead><tr><th>Source</th><th>Signal</th><th class="num">Confidence</th></tr></thead>
<tbody>{evidence_rows}</tbody></table></div>

<div class="section"><h2>📊 Quality Issues</h2>
<p class="sub">{h(kw['analyze_summary'])}</p>
<table><thead><tr><th>Rule</th><th>File</th><th>Severity</th><th>Message</th></tr></thead>
<tbody>{issue_rows}</tbody></table></div>

<div class="section"><h2>📈 Technical Debt Breakdown</h2>
{bar('AI Code Ratio', b.get('ai_code_ratio',0)*100)}
{bar('Test Coverage', b.get('test_coverage',0)*100, coverage_label(b.get('test_coverage',0)))}
{bar('Duplication Rate', b.get('duplication_rate',0)*100)}
<table><tbody>
<tr><td>Defect Density</td><td class="num">{b.get('defect_density',0):.1f} / KLOC</td></tr>
<tr><td>Critical Issues</td><td class="num">{b.get('critical_issues',0)}</td></tr>
</tbody></table></div>

<footer>
  Generated by <a href="https://github.com/open-delivery-spec/validate-action">ODS validate-action</a> ·
  {generated} · Signals are heuristic — ODS is a signal producer, not a quality oracle.
</footer>
</body></html>"""


if __name__ == "__main__":
    result_value = main()
    # Expose result_value to the caller via env file
    with open(os.path.join(sys.argv[1], ".result"), "w") as f:
        f.write(result_value)
