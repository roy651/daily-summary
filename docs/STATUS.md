# Project Status — daily-summary

_Snapshot: 2026-06-05. Audience: future maintainers + the project owner._

## Mission (recap)

Read Avigail's (studio **ula**) daily correspondence and produce a read-only morning digest:
project status + last-24h updates + a prioritized TODO list. Sibling to `invoicing-assistant`;
shares the portable `mail-evidence` input layer.

## Where we are

**Phase 0 — Scaffold (in progress).** Repo skeleton + conventions mirrored from the sibling.
Nothing reasons yet.

## Key decisions

- Hybrid reasoning designed toward headless (`REASONER=session|api|replay`).
- Delivery abstraction with file (default) + email backends (`DELIVERY=file|email`); both plumbings
  built now, email flag-off.
- JSON state (divergence from the sibling's CSV — see `docs/01`).
- Project→Task→Todo hierarchy with optional tasks; scope ambiguity surfaced, not failed.
- No invoice-style oracle → we manufacture ground truth from a held-out week (`docs/07`).

## Deferred (phase 2)

Learning loop (consume feedback), EmailDelivery go-live, ApiReasoner go-live, online GT loop,
Hermes delegation, WhatsApp, mail-evidence extraction to a standalone lib.

## Next checkpoint

Close Phase 0 (pytest green, mail-evidence importable), then build Phase 1 test-first.
