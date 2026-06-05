# 01 — State model

Canonical schema for the domain state. Code: `digest/digest_core/state.py`. **Read this before
touching state.** (Status: stub — fill in alongside the `state.py` implementation task.)

## Storage = JSON, one file per entity, under `state/` (git-ignored)

Deliberate divergence from the sibling's CSV. Rationale (do **not** "correct" this back to CSV):
- Entities are **nested and ragged** — a Project holds lists of tasks, blockers, todos, evidence
  ids, observations. CSV forces lossy flattening or sidecar tables.
- The MODEL PASS returns JSON, so `apply` is a near-isomorphic merge, not a flatten/unflatten dance.
- No spreadsheet target drives CSV here (the sibling's CSV mirrored a Google Sheet).
- JSON stays human-readable and round-trip-safe, so hand-editing `state/*.json` is a valid manual
  override path during the supervised phase.

Reject YAML (whitespace-fragile for machine writes) and SQLite (no query layer to justify it yet).

## Hierarchy: Project → Task → Todo

Distinguishing a *project* (a client engagement / deliverable scope, long-lived) from a *task*
(a unit of work within it) is genuinely hard. We don't force it: a Project has `0..n` Tasks; a
Todo (concrete next-action) attaches to a Task when the model is confident of the grouping, else
hangs directly off the Project. Scope ambiguity is an accepted, surfaced uncertainty — never a
hard failure.

## Three-way separation (borrowed from the sibling's ledger)

- **observed-truth** — what the evidence literally shows (`last_activity_date`, evidence ids).
- **agent-proposed** — the model's inferred read, rewritten each run (`status_agent`, `confidence`).
- **human-confirmed** — Avigail's overrides; written ONLY via the feedback channel, never by the
  deterministic layer (a unit test enforces this).

## Entities (filled in with the implementation)

- `ClientProfile` — `state/clients.json`
- `Project` (+ embedded `Task`, `Blocker`, `Todo`) — `state/projects.json`
- `observations: [{date, source, note}]` on clients/projects/tasks — soft tacit knowledge + the
  landing zone for corrections and the future learning store.

`load_*`/`write_*` round-trip exactly (None↔null, stable key order) — pinned by a unit test.
