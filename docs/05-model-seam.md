# 05 — Model seam

Code: `digest/digest_core/{reasoner,schema,apply}.py`.

## Reasoner Protocol (env-selected: `REASONER=code|api|session|replay`)

`Reasoner`: `reason(packet: ReasoningPacket) -> ModelOutput`. All four backends produce the SAME
`ModelOutput` from the same packet (drop-in equivalent — swapping is an env change, never code). The
model-facing contract (`_REASONER_SYSTEM` + `MODEL_OUTPUT_SCHEMA`) is shared by the `code` and `api`
backends. `select_reasoner` falls back to `session` when `REASONER` is unset; the shipped `.env`
selects `code`. Output is single-use (archived to `model_output.<date>.json`, packet deleted;
`generated_at` must equal the run date).

- **CodeReasoner** (`code`) — headless Claude Code (`claude -p`) under the user's **subscription, no
  API key**. Runs in a scratch dir (`work_dir/.reasoner`) with `cwd`/`--add-dir` scoped to it; one
  reprompt-on-bad-JSON retry, stdout logged.
- **ApiReasoner** (`api`) — provider-agnostic: `LLM_PROVIDER=anthropic` (Anthropic SDK, tool-forced)
  or `openai` (any OpenAI-compatible endpoint — OpenRouter / Together / local — via `LLM_BASE_URL` +
  `LLM_MODEL` + `LLM_API_KEY`). Behind the `api` extra (`uv sync --extra api`). The Anthropic key is
  never sent to a third-party endpoint (provider-gated).
- **SessionReasoner** (`session`, supervised fallback) — writes `packet.json`; the in-session model
  emits `model_output.json`; loads + validates it (raises `SessionPending` until present).
- **ReplayReasoner** (`replay`, tests) — loads a fixture `model_output.json`; runs end-to-end offline.

## ReasoningPacket (model input — pure data)

`{run_date, window, current_projects[], clients[], contacts[(email, role)], threads[(records with
direction)], glossary}`. Built by `packet.py`; no formatting (that's `render.py`).

## ModelOutput schema (validated by `apply.py`)

`project_updates[]` (each: `project_id|null` — null = newly discovered, requires
`client_id/end_client/title`; `status_agent`, `status_evidence`, `confidence`, `blockers`,
`deadline`, `evidence_thread_ids`, `closed_todos[]`, `todos[]`), `digest_updates[]`,
`unresolved[]` (each tagged `kind` ∈ `{unplaced, personal, lead, entity}` so the digest can route
them), and **`corrections[]`** — the self-reconciliation channel (below).

## Corrections — the model self-heals (and so does Avigail)

`corrections[]` (`kind` ∈ `{retract_knowledge, merge_contacts}`) let the reasoner undo its own past
mistakes when a confirmed note or clear evidence contradicts an existing fact/role:
- `retract_knowledge {match, note?}` → `knowledge.supersede` drops the stale note (optionally adds a
  corrected one).
- `merge_contacts {emails, role}` → `contacts.merge` links the addresses to one canonical entity and
  sets the shared role.

`apply_corrections` runs the same channel for Avigail's feedback (`source="feedback"`) and the model
(`source="model"`). **Provenance-ranked** (`state.SOURCE_RANK`, `docs/01`): a model correction can
purge only model/agent/auto facts — never an `[AVIGAIL-CONFIRMED]` one — and can't downgrade a
stronger-sourced role. The system prompt instructs the model to obey `[AVIGAIL-CONFIRMED]` notes,
consolidate duplicate knowledge, infer roles from billing direction (C2) and entity context, and
surface uncertain threads (recall-first) rather than drop them.

## apply.py safety rules

Match by `project_id` else `(client_id, normalized-title)` overlap (no duplicate projects); write
ONLY observed + agent-proposed columns; **assert human-confirmed columns are never written**;
recompute `last_activity_date` from cited in-window evidence (not the model); reject unknown enums /
missing required fields → fail the run loudly (never guess).
