# Handoff — daily-summary (planning seed)

You are starting a **new, standalone product**. This file is the only context that
exists yet. Read it fully before planning. The sibling project it borrows from lives at
`../private/invoicing-assistant` — reference it, do **not** fold into it.

## Mission (seed — refine in the plan)

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

### First architectural decision for the plan: how to share it

Don't copy/vendor `mail-evidence` — it will drift from the original and you'd maintain
conditioning logic twice. Pick a real dependency mechanism:

1. **Extract `mail-evidence` into a standalone shared library** (own repo / installable
   package) that *both* products depend on. Cleanest long-term; a small up-front lift, and
   it touches invoicing-assistant (move the package, repoint its imports).
2. **git submodule** of invoicing-assistant (or just its `skills/mail-evidence/`) — fast,
   no extraction, but couples the two repos' layout.
3. **Local editable install** (`uv pip install -e ../private/invoicing-assistant/skills/mail-evidence`)
   — fastest to start planning/prototyping; revisit before the products diverge.

Recommendation: start on (3) to unblock planning, design toward (1). Whatever you choose,
the **portability guard must keep passing** — never add a daily-summary import into the
package; inject via the protocols instead.

Same logic applies later to `skills/transcripts/` (the Zoom layer) — also portable, also
shared.

## Reference material in invoicing-assistant (read, don't copy)

- `docs/STATUS.md` — zoom-out on the sibling: what's built, the gaps, the deferred work.
- `docs/RUNBOOK.md` — how a monthly run actually operates (the input-fetch steps mirror
  what daily-summary needs).
- `skills/mail-evidence/` + its `tests/` and `mail-evidence-SPEC` doc — the package contract.
- `CLAUDE.md` — note its *shape* (lean always-on context + `docs/` pointers, hard safety
  invariants). Adopt the structure; write your own content.

## Suggested first planning steps (not prescriptive)

1. Write this repo's own `CLAUDE.md`: mission, read-only/privacy invariants, repo map.
2. Open the plan with a **"Shared foundations"** section: adopt `mail-evidence` as the input
   layer, pick the sharing mechanism above, define the daily-summary `RelevanceJudge` /
   `ContactStore` implementations.
3. Then design the daily-summary–specific layer: digest reasoning, to-do projection,
   daily cadence/scheduling, and how the output is delivered to Avigail.

## Guardrails to carry over

- **No secrets in the repo.** Credentials via Keychain / git-ignored `.env`; real
  correspondence stays in a git-ignored `fixtures/`-style dir. (Mirror invoicing-assistant's
  gitleaks + pre-commit setup.)
- **Read-only on the mailbox.** `mail-evidence` fetch uses IMAP EXAMINE; keep it that way.
