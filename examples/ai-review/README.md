# Reference recipe: AI review → ODS gate

This wires **your own** LLM's code review into the ODS merge gate. The reviewer
produces a [`review-verdict/v1`](https://github.com/open-delivery-spec/spec/blob/main/schemas/review-verdict/v1.json)
file; ODS ingests it as `input.ai_reviews` and routes review attention —
advisory by default, **it can only tighten the gate, never merge on its own**
(see the [positioning](https://github.com/open-delivery-spec/spec/blob/main/POSITIONING.md)).

Bring your own model and key. This is a *swappable convenience*, not the core
value — replace it with CodeRabbit, Copilot code review, or any reviewer that
can emit `review-verdict/v1`.

## Pieces

- [`review-prompt.md`](review-prompt.md) — the prompt (ask any LLM for a verdict).
- [`../../scripts/to-verdict.py`](../../scripts/to-verdict.py) — a tolerant
  normalizer: turns the model's best-effort output into a schema-valid verdict
  (fills `schema`/`reviewer`, stamps `head_sha`, validates the enums, drops junk).

## Synchronous recipe (recommended — no re-trigger needed)

Run the review **in the same job** as the gate, so everything happens in one
pass and PR comments never need to re-trigger anything:

```yaml
name: ODS with AI review
on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  ods:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0

      # 1. Review the diff with your LLM of choice. Example with the Claude CLI;
      #    swap in any model. ANTHROPIC_API_KEY is your secret.
      - name: AI review
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          git diff origin/${{ github.base_ref }}...HEAD > pr.diff
          # Feed the prompt + diff to your model; capture raw output.
          claude -p "$(cat validate-action/examples/ai-review/review-prompt.md)" < pr.diff > raw.txt || true
          # Normalize to a schema-valid verdict, stamped with the PR head SHA.
          python3 validate-action/scripts/to-verdict.py raw.txt \
            --tool claude-code \
            --head-sha "${{ github.event.pull_request.head.sha }}" \
            --out ai-review.json

      # 2. Gate. The verdict flows into the policy as input.ai_reviews.
      - uses: open-delivery-spec/validate-action@v1
        with:
          ai-review: ai-review.json
          review-routing: "true"   # act on the elevated tier
```

## What about async reviewers (CodeRabbit, Copilot code review)?

Those bots post PR comments on **their** schedule, after ODS has already run,
and re-review when someone replies. To consume them you'd re-run the gate on
`pull_request_review` / `issue_comment` events and read the bot's output — and
ODS's `head_sha` matching already skips verdicts stamped for an old commit. But
ODS deliberately **does not ship per-vendor comment scrapers**: parsing another
tool's free-text comments is fragile and vendor-coupled. If a reviewer can emit
`review-verdict/v1` (directly or via a converter you control), it plugs in the
same way as above. See the
[positioning doc](https://github.com/open-delivery-spec/spec/blob/main/POSITIONING.md)
for why.
