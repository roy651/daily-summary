# 07 — Acceptance & evaluation

The deterministic gate is the golden offline oracle below; the manufactured ground-truth set tunes
digest quality. 180 tests green at the time of writing.

## Golden offline oracle

`digest/tests/test_daily_golden.py`: offline emails (`ingest_email_export(tests/fixtures/emails)`)
→ packet → `ReplayReasoner` → `apply` → `render`, asserted against `expected_digest.md` +
`expected_todos.json`. This is the deterministic CI gate.

## Ground truth (we manufacture it — there is no invoice-style oracle here)

1. **Backtest the held-out week.** After bootstrap (which holds out the last ~7 days), replay each
   day in order via `cli daily --as-of <date>` to produce 7 dated digests.
2. **Collect Avigail's truth per day** into `eval/gt/<date>.{md,json}` — her edits/feedback or, ideally,
   her own GT version of each day's digest/todos.
3. **Score** with a recall-oriented scorer (`cli score`; recall is the gate, precision informational):
   did the digest surface the projects/updates/todos in the GT? Per-day + aggregate.
4. **Manual now, online soon** — run the loop manually to tune v1, then move it online as the
   standing feedback loop.
