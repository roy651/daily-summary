# 02 — Pipeline

Code: `digest/digest_core/{bootstrap,daily,cli}.py`.

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
- **The window is automatic** (`_digest_window_since`): ≥ 2 days, extended back to the oldest
  per-account watermark, warns if the span exceeds ~31 days. Override with `--since` / `--window-days`.

Steps (`daily.run_digest`):

1. **PULL** — multi-account (`IMAP_ACCOUNTS`), read-only EXAMINE, per-account watermark.
2. **CONDITION** — `unify` → date-sorted records; drop `is_self_generated` (our own digests/replies).
3. **CONSUME FEEDBACK** (before the packet) — close todos, archive/revive, collect `suppress:`, route
   free-text notes → knowledge, and `apply_corrections` from Avigail (`source="feedback"`).
4. **SUPPRESS** — drop threads in `suppressed.json` so the reasoner never sees flagged-off mail.
5. **BILLING** — `apply_billing_signals` infers roles from invoice direction (C2) before the packet.
6. **PACKET** — `build_reasoning_packet`, including knowledge notes (`[AVIGAIL-CONFIRMED]` tagged).
7. **MODEL PASS** — `reasoner.reason(packet) -> ModelOutput` (the one swappable seam, `docs/05`).
8. **APPLY** — guarded merge (`apply_model_output`), tacit insights, then `apply_corrections` from the
   model (`source="model"`, rank-guarded so it can't clobber confirmed facts).
9. **RENDER** — `out/digest_<date>.md` + `out/todos.md` (with the feedback template) +
   `out/state-review.md` (regenerated every run).
10. **DELIVER** (file | email) → **PERSIST** projects/clients/contacts/knowledge/suppressed +
    **commit each account's watermark only after delivery succeeds** (crash → re-pull ≤1 batch,
    idempotent by Message-ID).

`--dry-run` runs everything but doesn't send, persist, or advance the watermark (writes `out/` to
read). `cli daily --as-of DATE` replays a past day deterministically (for the GT backtest).
