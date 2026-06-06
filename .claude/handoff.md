# Handoff — daily-summary

**The product is built** (Phase 1 complete, feedback loop closed — see `docs/STATUS.md` for the
zoom-out and `docs/06-build-plan.md` for the current phase). This file is the durable orientation to
the **shared `mail-evidence` foundation** and why this is its own repo. For how the system works
day-to-day, read `docs/00-overview.md` → `07` and `docs/RUNBOOK.md`. The sibling it borrows from lives
at `../private/invoicing-assistant` — reference it, do **not** fold into it.

## Mission

A **daily business summary** for Avigail (freelance design studio "ula"): read her daily
correspondence and produce a short morning digest of *what happened* + *what she likely
owes action on* (projected to-dos). Input channels are email today, Zoom transcripts later.
Output is a **read-only digest** — it informs, it does not act.

This is a *different product* from invoicing-assistant (which prepares draft invoices).
Same person, same mailbox, same input layer — different output, different cadence (daily
vs monthly), different risk profile.

## Why this is a separate repo (not folded into invoicing-assistant)

- **Different gate model / safety profile.** invoicing-assistant's entire `CLAUDE.md` is
  built around "never auto-bill; the human gate is the proforma→invoice conversion." That
  product writes (draft proformas) to an external billing system. **daily-summary writes
  nothing external** — it reads mail and emits a summary. Its safety story is *privacy +
  read-only*, not *billing gates*. Inheriting the invoicing invariants would be wrong.
- **Different mission, cadence, docs, git history.** It deserves its own `CLAUDE.md`,
  `docs/`, and clean history.

So: keep this as its own folder/repo. Point at invoicing-assistant for the **shared input
layer** and for proven patterns — nothing more.

## The shared foundation: `mail-evidence`

The single biggest reuse is the **`mail-evidence`** package, already built and validated in
invoicing-assistant. It was deliberately built **portable and import-clean** (the "1.6.5
portability boundary"): no invoicing / morning / Google / billing coupling — a guard test
fails the build if such an import sneaks in. It exists in a reusable shape *on purpose*, for
exactly this second consumer.

Location: `../private/invoicing-assistant/skills/mail-evidence/`

What it does: mail → conditioned **evidence**. Multi-account IMAP fetch (INBOX + Sent),
References-chain threading, in-thread quote dedup, header-based relevance tiering (T1
known-contact / T2 unknown-human / T3 bulk), and a watermarked live runner.

Public API (`from mail_evidence import ...`):

| Symbol | Role |
| --- | --- |
| `EvidenceRecord`, `Thread`, `AttachmentMeta`, `RelevanceDecision` | Data model. One record = one email/transcript; one `Thread` = one conversation. |
| `RelevanceJudge`, `ContactStore` (Protocols) | **Injected by the consumer.** This is the seam: *you* supply the relevance judgment + contact knowledge. The package defines only the contract. |
| `FetchConfig`, `fetch_messages`, `ImapClient` | IMAP fetch (multi-folder, read-only / EXAMINE). |
| `ingest_email_export` | Offline `.eml`/`.mbox` ingestion — byte-identical records to live. Use this for fixtures/tests. |
| `assemble_threads`, `dedup_in_thread`, `classify_tier`, `condition` | The conditioning pipeline stages. |
| `run` | Full pipeline iterator (fetch → assemble → dedup → tier → condition). |
| `load_watermark`, `commit_watermark` | Crash-safe incremental fetch. |
| `mail_evidence.runner` (CLI) | `probe` / `fetch` / `watermark` — the live multi-account entry point. |

The `RelevanceJudge` / `ContactStore` protocols are the key design point: domain logic
(what counts as "relevant" for a daily summary vs for billing) lives in the consumer, not
the package. daily-summary supplies its *own* judge — "is this thread worth surfacing in
today's digest" is a different question than "is this billable work."

### How it's shared (decided)

We use a **local editable install** of the sibling's package
(`../private/invoicing-assistant/skills/mail-evidence/`, wired in `pyproject.toml`) — the fastest
mechanism, with extraction to a standalone shared library as the long-term direction (see
`docs/06`/`STATUS` deferred). Don't copy/vendor it (it would drift). The **portability guard must keep
passing** — never add a daily-summary import into the package; inject via the `RelevanceJudge` /
`ContactStore` protocols instead (`relevance.py` / `contacts.py`).

Same logic applies later to `skills/transcripts/` (the Zoom layer, Phase 1.5) — also portable, also
shared.

## Reference material in invoicing-assistant (read, don't copy)

- `docs/STATUS.md` — zoom-out on the sibling: what's built, the gaps, the deferred work.
- `docs/RUNBOOK.md` — how a monthly run actually operates (the input-fetch steps mirror
  what daily-summary needs).
- `skills/mail-evidence/` + its `tests/` and `mail-evidence-SPEC` doc — the package contract.
- `CLAUDE.md` — note its *shape* (lean always-on context + `docs/` pointers, hard safety
  invariants). Adopt the structure; write your own content.

## Where to look now (the build is done)

- `CLAUDE.md` — lean always-on invariants + repo map (start here every session).
- `docs/00-overview.md` → `07` — the design docs (state, pipeline, todos, delivery, model seam,
  build plan, acceptance). `docs/RUNBOOK.md` — how to operate it.
- `docs/reviews/` — the milestone review history (Reviews 1–5 + fix cycles).
- `digest/digest_core/` — the code; `digest/tests/` — the suite (180 green).

## Guardrails (still in force)

- **No secrets in the repo.** Credentials via Keychain / git-ignored `.env`; real
  correspondence stays in a git-ignored `fixtures/`-style dir. (Mirror invoicing-assistant's
  gitleaks + pre-commit setup.)
- **Read-only on the mailbox.** `mail-evidence` fetch uses IMAP EXAMINE; keep it that way.
