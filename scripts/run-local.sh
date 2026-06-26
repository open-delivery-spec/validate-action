#!/usr/bin/env bash
#
# run-local.sh — run the ODS pipeline locally, exactly as validate-action runs it
# in CI, but without GitHub Actions. Lets you iterate on detection and policy
# before pushing a PR.
#
# It runs detect → analyze → score → check into an output directory, then renders
# the same HTML/Markdown report the Action produces. Exits non-zero if the policy
# blocks the change.
#
# Usage:
#   scripts/run-local.sh [--diff-base <ref>] [--branch <name>] [--policy <file>]
#                        [--commits <n>] [--output-dir <dir>]
#                        [--pr-body <text> | --pr-file <path>]
#
# Examples:
#   scripts/run-local.sh                          # diff against origin/main
#   scripts/run-local.sh --diff-base HEAD~3       # last 3 commits
#   scripts/run-local.sh --policy .ods/policy.rego
#
set -euo pipefail

DIFF_BASE="${ODS_DIFF_BASE:-origin/main}"
BRANCH=""
POLICY="${ODS_POLICY:-}"
COMMITS="${ODS_COMMITS:-10}"
OUTPUT_DIR="${ODS_OUTPUT_DIR:-.ods/out}"
PR_BODY="${ODS_PR_BODY:-}"
PR_FILE=""

usage() {
  sed -n '2,/^set -euo/p' "$0" | sed 's/^# \{0,1\}//; s/^#$//' | sed '$d'
}

while [ $# -gt 0 ]; do
  case "$1" in
    --diff-base)  DIFF_BASE="$2"; shift 2 ;;
    --branch)     BRANCH="$2"; shift 2 ;;
    --policy)     POLICY="$2"; shift 2 ;;
    --commits)    COMMITS="$2"; shift 2 ;;
    --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
    --pr-body)    PR_BODY="$2"; shift 2 ;;
    --pr-file)    PR_FILE="$2"; shift 2 ;;
    -h|--help)    usage; exit 0 ;;
    *) echo "error: unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

if ! command -v ods >/dev/null 2>&1; then
  echo "error: 'ods' not found on PATH." >&2
  echo "       install it with: go install github.com/open-delivery-spec/cli/cmd/ods@latest" >&2
  exit 127
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORT_SCRIPT="$SCRIPT_DIR/generate-report.py"

mkdir -p "$OUTPUT_DIR"

# Default branch to the current checkout.
if [ -z "$BRANCH" ]; then
  BRANCH="$(git branch --show-current 2>/dev/null || echo "")"
fi

# Export the values the CLI also reads from the environment.
export ODS_DIFF_BASE="$DIFF_BASE"
if [ -n "$BRANCH" ]; then
  export ODS_BRANCH="$BRANCH"
  export ODS_BRANCH_NAME="$BRANCH"
fi

# Build detect flags as an array so values with spaces survive intact.
detect_flags=(--diff-base "$DIFF_BASE" --commits "$COMMITS")
[ -n "$BRANCH" ] && detect_flags+=(--branch "$BRANCH")
if [ -n "$PR_BODY" ]; then
  detect_flags+=(--pr-body "$PR_BODY")
elif [ -n "$PR_FILE" ] && [ -f "$PR_FILE" ]; then
  detect_flags+=(--pr-file "$PR_FILE")
fi

echo "① detect"
# `ods detect` exits non-zero for high-confidence positives too, so don't let
# set -e abort here; validate the JSON instead and synthesize an inconclusive
# result if the output is missing/corrupt (matching the Action's behavior).
if ! ods detect --json "${detect_flags[@]}" > "$OUTPUT_DIR/detect.json" 2>"$OUTPUT_DIR/detect.stderr"; then :; fi
if ! python3 -c "import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if 'ai_generated' in d else 1)" "$OUTPUT_DIR/detect.json" 2>/dev/null; then
  echo "  warning: detection inconclusive (see $OUTPUT_DIR/detect.stderr)"
  printf '{"_ods_detect_error":true,"ai_generated":false,"confidence":0,"evidence":[],"sources":[],"summary":"Detection inconclusive"}\n' > "$OUTPUT_DIR/detect.json"
fi

echo "② analyze"
ods analyze --json 2>/dev/null > "$OUTPUT_DIR/analyze.json" || \
  echo '{"issues":[],"total_lines":0,"summary":"No code analyzed"}' > "$OUTPUT_DIR/analyze.json"

echo "③ score"
ods score --json 2>/dev/null > "$OUTPUT_DIR/score.json" || \
  echo '{"technical_debt_delta":0,"verdict":"neutral"}' > "$OUTPUT_DIR/score.json"

echo "④ check"
if [ -n "$POLICY" ] && [ -f "$POLICY" ]; then
  ods check --json --policy "$POLICY" > "$OUTPUT_DIR/check.json" 2>/dev/null || true
else
  ods check --json > "$OUTPUT_DIR/check.json" 2>/dev/null || true
fi

# Render the report (no GitHub output path → local mode).
python3 "$REPORT_SCRIPT" "$OUTPUT_DIR"

RESULT_VALUE="$(cat "$OUTPUT_DIR/.result" 2>/dev/null || echo pass)"
echo
echo "Result:  $RESULT_VALUE"
echo "Report:  $OUTPUT_DIR/index.html"
echo "Summary: $OUTPUT_DIR/ods-summary.md"

if [ "$RESULT_VALUE" = "block" ]; then
  echo "ODS policy blocked this change." >&2
  exit 1
fi
