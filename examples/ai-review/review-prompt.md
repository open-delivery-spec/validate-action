# ODS AI review prompt

Give this to any LLM (Claude Code `/review`, `claude -p`, `llm`, an OpenAI
call, …) together with the PR diff. Pipe the model's output through
`scripts/to-verdict.py` to get a schema-valid `review-verdict/v1` file the ODS
gate can consume. The normalizer is tolerant, so the model doesn't have to emit
perfect JSON — but asking for this shape gets the best results.

---

You are a code reviewer. Review the diff below for **correctness** (logic
errors, unhandled edge cases, race conditions), **security**, and **design**.
Focus on what a careful human reviewer would flag; ignore style nits a linter
already covers.

Respond with **only** a JSON object in this shape, no prose:

```json
{
  "verdict": "approve | request_changes | comment",
  "findings": [
    {
      "file": "path/to/file",
      "line": 42,
      "severity": "info | low | medium | high | critical",
      "category": "correctness | security | design | test-coverage",
      "message": "What is wrong and why it matters.",
      "suggestion": "Concrete fix, if you have one."
    }
  ]
}
```

Rules:
- Use `request_changes` only when you found a real correctness or security
  problem. Use `comment` for non-blocking observations. Use `approve` when you
  have no concerns.
- `message` is required on every finding; every other field is optional.
- If the change looks correct, return `"verdict": "approve"` and an empty
  `findings` list.

Diff to review:

<PASTE OR PIPE THE PR DIFF HERE>
