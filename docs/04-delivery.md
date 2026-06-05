# 04 — Delivery + feedback

Code: `digest/digest_core/{delivery,feedback}.py`. (Status: stub.)

## Delivery interface (env-selected: `DELIVERY=file|email`)

`Delivery`: `deliver(digest_md, todos_md, *, run_date)` + `collect_feedback() -> list[FeedbackRecord]`.

- **FileDelivery (default, MVP):** writes `out/digest_YYYY-MM-DD.md` (informational) + editable
  `out/todos.md`; `collect_feedback` diffs the edited file next run. No network.
- **EmailDelivery (built now, flag-off):** sends the digest; next run's `collect_feedback` reads
  Avigail's reply via the same `mail-evidence` read path (her reply is just another inbound thread).

## Outbound guarding (kept simple)

The app-password risk already exists from *reading* the mailbox, so outbound is not a new threat
surface. The only invariant: **recipient = Avigail's own address** (`DIGEST_EMAIL_TO` allowlist; a
non-allowlist recipient raises). Outbound SMTP is a separate path from the read-only IMAP layer;
`DRY_RUN=1` returns would-send without sending; a `digest:` subject tag lets re-reads recognize and
drop our own outbound (`is_self_generated`). Because the guard is simple, `DELIVERY=email` can go
live whenever the digest is good enough.

## Feedback parser (captured in v1, consumed in phase 2)

`parse_reply`/`parse_todos_md` → `FeedbackRecord {run_date, revised_todos[], eod_actuals[],
suppressed_threads[], freeform_notes}`, persisted to `state/feedback/`. `suppressed_threads` is how
Avigail flags off an over-surfaced email. v1 builds the channel + schema; *applying* feedback into
reasoning / overrides is the phase-2 learning line (see `06-build-plan.md`).
