# fixtures/ (git-ignored)

Holds **real correspondence** and live-derived data for local development. Everything here except
this README is git-ignored — it is PII and must never be committed.

Typical contents:
- `emails/INBOX/*.eml`, `emails/Sent/*.eml` — exports pulled by `mail_evidence.runner fetch`.

For the one-time cold-start bootstrap, daily-summary reads the **sibling's** export
(`SIBLING_EXPORT_ROOT`, default `../private/invoicing-assistant/fixtures/emails`) once; thereafter
it pulls independently into this directory.

Synthetic, committable test fixtures live under `digest/tests/fixtures/`, not here.
