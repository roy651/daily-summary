# 02 — Pipeline

Code: `digest/digest_core/{bootstrap,daily,cli}.py`. (Status: stub — fill in with the
implementation tasks.)

## Bootstrap (one-shot, `--holdout-days 7`)

`ingest_email_export(SIBLING_EXPORT_ROOT)` → condition → group correspondents into candidate
clients → seed `DigestContactStore` → MODEL PASS (bootstrap variant) → write
`clients.json`/`projects.json`/`contacts.json`. Consumes data up to ~7 days ago; the most recent
week is held out for ground-truth collection (see `07-acceptance.md`). `--force` guards against
clobbering accumulated state. Only sibling touchpoint: a one-time file read.

## Daily (recurring) — two distinct windows

- **Ingestion window = the watermark.** Each run fetches everything new since the last committed
  watermark (gap-free, no double-processing). The watermark advances only after delivery succeeds;
  a crash re-pulls ≤1 batch (idempotent by Message-ID). No fixed overlapping window.
- **Report window = since the last successful digest** (~24h, longer if a run was skipped) — what
  to *highlight*. The model also always sees the full current state of every open project
  (carry-forward), so on-hold/long-running projects stay in context with zero new mail.

Steps: PULL → CONDITION (`unify`, drop `is_self_generated`) → PACKET → MODEL PASS → APPLY
(guarded) → RENDER → DELIVER → PERSIST (state + contacts + commit watermark).

`cli daily --as-of DATE` replays a past day deterministically (for the GT backtest).
