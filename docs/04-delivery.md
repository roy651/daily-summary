# 04 — Delivery + feedback

Code: `digest/digest_core/{delivery,feedback}.py`.

## Delivery interface (env-selected: `DELIVERY=file|email`)

`Delivery`: `deliver(digest_md, todos_md, *, run_date)` + `collect_feedback() -> list[FeedbackRecord]`.

- **FileDelivery (default, MVP):** writes `out/digest_YYYY-MM-DD.md` (informational) + editable
  `out/todos.md`; `collect_feedback` diffs the edited file next run. No network.
- **EmailDelivery (built now, flag-off):** sends the digest; next run's `collect_feedback` reads
  Avigail's reply via the same `mail-evidence` read path (her reply is just another inbound thread).

## Outbound guarding (kept simple)

The app-password risk already exists from *reading* the mailbox, so outbound is not a new threat
surface. The only invariant: **recipient = Avigail's own address** (`DIGEST_EMAIL_TO` allowlist; a
non-allowlist recipient raises). Outbound SMTP is a separate path from the read-only IMAP layer; a
single **`--dry-run`** knob runs everything but doesn't send/persist/advance the watermark; a
`digest:` subject tag lets re-reads recognize and drop our own outbound (`is_self_generated`).

## Feedback — consumed (closed loop)

`parse_reply` (email) / `parse_todos_md` (file) → `FeedbackRecord {run_date, revised_todos[],
eod_actuals[], suppressed_threads[], corrections[], freeform_notes}`. Avigail's reply is recognized by
the `digest:` subject tag (from her address) and never read as project evidence. The loop is **closed**
— `daily` applies feedback before the model pass (`docs/02` step 3). Directives (`#`-prefixed in the
file, bare in an email reply):

- `done: …` — close a todo · `archive: <project-id>` / `revive: <id>` · `suppress: <thread-id>` —
  hide a thread (persisted to `suppressed.json`).
- `forget: <text>` — **retract a wrong fact** from knowledge (a `retract_knowledge` correction).
- `alias: a@x.com, b@y.com = subcontractor` — **declare addresses are one entity** + set the role (a
  `merge_contacts` correction).
- any other prose → a **knowledge note**, tagged `[AVIGAIL-CONFIRMED]` so the reasoner trusts it over
  its own guess and reconciles contradictions (the correction mechanism, `docs/05`).

The render appends a feedback template to `out/todos.md` with placeholders that auto-clear, so the
file backend always has the directive syntax at hand.
