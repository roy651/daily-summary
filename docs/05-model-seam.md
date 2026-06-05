# 05 — Model seam

Code: `digest/digest_core/{reasoner,schema,apply}.py`. (Status: stub.)

## Reasoner Protocol (env-selected: `REASONER=session|api|replay`)

`Reasoner`: `reason(packet: ReasoningPacket) -> ModelOutput`.

- **SessionReasoner** (v1 default) — writes `packet.json` to a known path; the in-session model
  reads it and emits `model_output.json`; loads + validates it.
- **ApiReasoner** (phase 2) — Anthropic API / Agent SDK, behind the `api` extra. Same packet in,
  `ModelOutput` out. Consult the claude-api reference for current model ids before wiring.
- **ReplayReasoner** (tests) — loads a fixture `model_output.json`. Mirrors the sibling's
  `ReplayReasoner`; lets the daily job run end-to-end offline with no live model.

## ReasoningPacket (model input — pure data)

`{run_date, window, current_projects[], clients[], contacts[(email, role)], threads[(records with
direction)], glossary}`. Built by `packet.py`; no formatting (that's `render.py`).

## ModelOutput schema (validated by `apply.py`)

`project_updates[]` (each: `project_id|null` — null = newly discovered, requires
`client_id/end_client/title`; `status_agent`, `status_evidence`, `confidence`, `blockers`,
`deadline`, `evidence_thread_ids`, `todos[]`), `digest_updates[]`, `unresolved[]`.

## apply.py safety rules

Match by `project_id` else `(client_id, normalized-title)` overlap (no duplicate projects); write
ONLY observed + agent-proposed columns; **assert human-confirmed columns are never written**;
recompute `last_activity_date` from evidence (not the model); reject unknown enums / missing
required fields → fail the run loudly (never guess).
