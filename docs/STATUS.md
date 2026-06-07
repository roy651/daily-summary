# Project Status — daily-summary

_Snapshot: 2026-06-08. Audience: future maintainers + the project owner._

> **Now:** Digest reshaped to Avigail's spec + going live. **Phase-2 dashboard (`digest_web/`) is BUILT
> + tested (196 green)** — view + interact (todo CRUD, status, notes, revive) as tombstones on the
> single shared state model. **Pending deploy to the mini-pc** (SSH blocked under VSCode → continuing in
> the CC terminal); the morning cron + first email are gated on that. See `.claude/handoff.md`
> "ACTIVE WORK" and `docs/08-dashboard.md`. Nothing pushed.

## Mission (recap)

Read Avigail's (studio **ula**) daily correspondence and produce a read-only morning digest:
project status + last-~24h updates + a prioritized TODO list. Sibling to `invoicing-assistant`;
shares the portable `mail-evidence` input layer.

## Where we are

**Phase 1 — MVP + evaluation harness: complete, and the feedback loop is closed.** 180 tests
green. The whole loop runs end-to-end **against real mail**: pull (multi-account, read-only EXAMINE)
→ condition → reasoning packet → MODEL PASS → guarded apply → render (project status + ~24h updates +
prioritized todos) → deliver → persist. A golden test reproduces a fixed digest + prioritized todos;
the ground-truth backtest scorer is in place. CLI: `bootstrap | daily | feedback | review | score |
show`.

Built since the MVP (Reviews 3–5):

- **Headless model seam.** `REASONER=code` (headless Claude Code `claude -p`, runs under the
  subscription, no API key — the shipped `.env` default) and `REASONER=api` (provider-agnostic:
  Anthropic SDK or any OpenAI-compatible endpoint / OpenRouter) joined `session` (supervised
  fallback) and `replay` (tests). Same `ModelOutput` from all four.
- **Closed feedback loop.** Avigail's reply (or `out/todos.md` edits) is consumed, not just
  captured: `done:` closes todos, `archive:`/`revive:`, `suppress:` hides a thread (persisted),
  `forget:`/`alias:` and free-text notes feed the knowledge store as authoritative.
- **Correction mechanism.** A confirmed note or clear evidence makes the reasoner (and Avigail)
  **retract** a stale knowledge fact and **merge** mis-identified contacts — so false facts don't
  linger (the Rock-Design = Idan case). Provenance-ranked: human > billing > model/auto, enforced in
  both the contact and knowledge stores.
- **C2 billing-direction.** Invoice direction is the cleanest role signal: inbound invoice → sender
  is a subcontractor (authoritative); outbound → recipient is a payer (only fills an unknown role).
- **Closure/decay** of stale projects/todos; **knowledge store** of cross-client tacit facts fed into
  every packet; **state-review** (`out/state-review.md`) regenerated every run with a contacts-&-roles
  section.

Reviews 1–5 complete (`docs/reviews/`); Review 5 fix cycle (M1 knowledge provenance guard, M2 alias
role resolution, M3 retract echo) landed. Not yet run unattended on a schedule.

## Key decisions

- Hybrid reasoning, designed toward headless (`REASONER=code|api|session|replay`).
- Delivery abstraction with file (default) + email backends (`DELIVERY=file|email`); email recipient
  is allowlisted to Avigail's own address.
- JSON state (divergence from the sibling's CSV — see `docs/01`).
- Project→Task→Todo hierarchy with optional tasks; scope ambiguity surfaced, not failed.
- Recall is the gate (over-surface; Avigail prunes via feedback); precision is informational.
- No invoice-style oracle → we manufacture ground truth from a held-out week (`docs/07`).

## Deferred / follow-ups

- **J6+J7** — one configurable, domain-keyed **sender mute-list**, replacing the hard-coded
  `meydata` denoise *and* the grow-forever per-thread `suppressed.json` (do together).
- **J8** — close the `api`/OpenAI path with a canned-response fixture test (it is unit-only today).
- **J5** — cap/age the knowledge store. **J1** — optional reuse-archived-`model_output` idempotency.
- **Phase 1.5** — Zoom transcripts into `unify()`.
- **Phase 2** — Hermes delegation; WhatsApp; mail-evidence extraction to a standalone lib.

## Next checkpoint

First sustained **unattended `code`-backend run** (the Review-5 re-review trigger), then schedule it.
