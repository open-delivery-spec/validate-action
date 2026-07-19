#!/usr/bin/env python3
"""Compute risk-tier calibration from merged PR outcomes.

This script closes the loop by comparing ODS predicted risk (embedded in
`<!-- ods-calibration ... -->` markers in ODS PR comments) with real outcomes
captured as PR labels after merge.

Outcome label convention:
  - high:   ods:outcome/high, ods:outcome/incident, ods:outcome/hotfix, ods:outcome/revert
  - medium: ods:outcome/medium, ods:outcome/rework
  - low:    ods:outcome/low, ods:outcome/clean
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CALIBRATION_RE = re.compile(r"<!--\s*ods-calibration\s+({.+?})\s*-->")

HIGH_LABELS = {"ods:outcome/high", "ods:outcome/incident", "ods:outcome/hotfix", "ods:outcome/revert"}
MEDIUM_LABELS = {"ods:outcome/medium", "ods:outcome/rework"}
LOW_LABELS = {"ods:outcome/low", "ods:outcome/clean"}


def parse_marker(comment_body: str):
    m = CALIBRATION_RE.search(comment_body or "")
    if not m:
        return None
    try:
        payload = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    risk = str(payload.get("predicted_risk", "")).lower()
    if risk not in {"low", "medium", "high"}:
        return None
    return payload


def classify_outcome(labels):
    names = {str(x).lower() for x in labels}
    if names & HIGH_LABELS:
        return "high"
    if names & MEDIUM_LABELS:
        return "medium"
    if names & LOW_LABELS:
        return "low"
    return None


def api_get_json(url: str, token: str):
    req = Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_merged_prs(repo: str, token: str, since_utc: datetime, max_prs: int = 200):
    out = []
    page = 1
    while len(out) < max_prs:
        qs = urlencode({"state": "closed", "sort": "updated", "direction": "desc", "per_page": 100, "page": page})
        items = api_get_json(f"https://api.github.com/repos/{repo}/pulls?{qs}", token)
        if not items:
            break
        stop = False
        for pr in items:
            merged_at = pr.get("merged_at")
            if not merged_at:
                continue
            merged_ts = datetime.fromisoformat(merged_at.replace("Z", "+00:00"))
            if merged_ts < since_utc:
                stop = True
                break
            out.append(pr)
            if len(out) >= max_prs:
                break
        if stop:
            break
        page += 1
    return out


def latest_ods_marker(repo: str, token: str, pr_number: int):
    qs = urlencode({"per_page": 100})
    comments = api_get_json(f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments?{qs}", token)
    marker = None
    for c in comments:
        payload = parse_marker(c.get("body") or "")
        if payload:
            marker = payload
    return marker


def calibration_matrix(rows):
    risks = ("low", "medium", "high")
    matrix = {p: {a: 0 for a in risks} for p in risks}
    for r in rows:
        matrix[r["predicted"]][r["actual"]] += 1
    return matrix


def metrics(rows):
    if not rows:
        return {"sample_count": 0}
    total = len(rows)
    exact = sum(1 for r in rows if r["predicted"] == r["actual"])
    pred_high = [r for r in rows if r["predicted"] == "high"]
    actual_high = [r for r in rows if r["actual"] == "high"]
    tp = sum(1 for r in rows if r["predicted"] == "high" and r["actual"] == "high")
    precision = tp / len(pred_high) if pred_high else None
    recall = tp / len(actual_high) if actual_high else None
    return {
        "sample_count": total,
        "exact_match": exact / total,
        "high_precision": precision,
        "high_recall": recall,
        "predicted_high_count": len(pred_high),
        "actual_high_count": len(actual_high),
    }


def recommendation(m, min_samples: int):
    n = m.get("sample_count", 0)
    if n < min_samples:
        return f"Need more labeled merged PR outcomes ({n}/{min_samples}) before auto-adjusting thresholds."
    hr = m.get("high_recall")
    hp = m.get("high_precision")
    if hr is not None and hr < 0.70:
        return "High-risk recall is low. Tighten routing: escalate more medium PRs when AI confidence/debt is elevated."
    if hp is not None and hp < 0.40:
        return "High-risk precision is low. Reduce noise: require corroborating high-severity/coverage/policy signals before elevated routing."
    return "Calibration looks stable. Keep thresholds; continue collecting labeled outcomes."


def to_pct(v):
    if v is None:
        return "N/A"
    return f"{v*100:.0f}%"


def build_markdown(report):
    m = report["metrics"]
    lines = [
        "## 🎯 Risk Calibration",
        "",
        f"- Window: last **{report['window_days']} day(s)**",
        f"- Samples (merged PRs with ODS marker + outcome label): **{m.get('sample_count', 0)}**",
        f"- Exact tier match: **{to_pct(m.get('exact_match'))}**",
        f"- High-risk precision: **{to_pct(m.get('high_precision'))}**",
        f"- High-risk recall: **{to_pct(m.get('high_recall'))}**",
        "",
        "### Confusion Matrix (Predicted × Actual)",
        "",
        "| Predicted \\ Actual | low | medium | high |",
        "|---|---:|---:|---:|",
    ]
    mat = report["matrix"]
    for p in ("low", "medium", "high"):
        lines.append(f"| {p} | {mat[p]['low']} | {mat[p]['medium']} | {mat[p]['high']} |")
    lines.extend([
        "",
        f"**Recommendation:** {report['recommendation']}",
        "",
        "_Outcome labels are manual ground truth (`ods:outcome/*`) added after merge._",
    ])
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="owner/repo")
    ap.add_argument("--token", default=os.getenv("GH_TOKEN", ""))
    ap.add_argument("--window-days", type=int, default=30)
    ap.add_argument("--min-samples", type=int, default=20)
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--out-md", required=True)
    args = ap.parse_args()

    since_utc = datetime.now(timezone.utc) - timedelta(days=args.window_days)
    try:
        prs = fetch_merged_prs(args.repo, args.token, since_utc)
    except HTTPError as e:
        sys.exit(f"failed to fetch merged PRs: {e}")

    rows = []
    for pr in prs:
        labels = [x.get("name", "") for x in pr.get("labels", [])]
        actual = classify_outcome(labels)
        if not actual:
            continue
        marker = latest_ods_marker(args.repo, args.token, pr["number"])
        if not marker:
            continue
        rows.append(
            {
                "pr": pr["number"],
                "merged_at": pr.get("merged_at"),
                "predicted": marker["predicted_risk"],
                "actual": actual,
                "predicted_tier": marker.get("predicted_tier"),
            }
        )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo": args.repo,
        "window_days": args.window_days,
        "samples": rows,
        "matrix": calibration_matrix(rows),
        "metrics": metrics(rows),
    }
    report["recommendation"] = recommendation(report["metrics"], args.min_samples)

    with open(args.out_json, "w") as f:
        json.dump(report, f, indent=2)
    with open(args.out_md, "w") as f:
        f.write(build_markdown(report))

    print(f"Wrote calibration report: {args.out_json}")


if __name__ == "__main__":
    main()

