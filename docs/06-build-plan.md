# 06 — Build plan

All phases are **test-driven** (failing test first) and end with a **milestone review**
(`docs/reviews/REVIEW-<date>.md` + commit list + external review + fix cycle, tagged `review-<date>`).

## Current phase

**Phase 1 — MVP + evaluation harness.** ✅ complete (pending milestone review). Next: Phase 1.5
(Zoom transcripts), or wire a real bootstrap run against the sibling export.

## Phase 0 — Scaffold

Repo skeleton, `pyproject.toml` (editable mail-evidence), pre-commit (gitleaks+ruff), `.gitignore`,
lean `CLAUDE.md`, `docs/` stubs, `docs/reviews/` convention.
*Accept:* `uv run pytest` green on the empty suite; `from mail_evidence import run,
ingest_email_export` works; the sibling's portability guard still passes.

## Phase 1 — MVP + evaluation harness

State model (Project→Task→Todo, JSON round-trip); `DigestContactStore`; `KeepAllHumanJudge` +
`is_self_generated`; `build_reasoning_packet`; `schema` + `apply` (with the no-confirmed-write
guard); `todos.prioritize`; `render`; **FileDelivery** + feedback parser (captured); `cli review`
surfacing; `SessionReasoner` + `ReplayReasoner`; `bootstrap` (holdout) + `daily` + `cli`. Committed
synthetic fixtures + golden test. **Ground-truth backtest harness** (held-out-week replay + per-day
GT + recall scorer).
*Accept:* end-to-end golden run reproduces `expected_digest.md` + `expected_todos.json`; `apply`
provably never writes a confirmed column; bad model output fails loudly; watermark commits only
after delivery; runnable in a supervised session.

## Phase 1.5 — Zoom transcripts (near-term priority)

Wire the sibling's portable `transcripts` skill into `unify()` so transcript `EvidenceRecord`s flow
into the same packet.
*Accept:* a transcript mentioning an approval/brief updates the right project in the golden test.

## Phase 2 — Deferred

Learning loop (consume `state/feedback/` overrides authoritatively into human-confirmed columns +
observations); EmailDelivery go-live (may pull earlier — guard is simple); `ApiReasoner` go-live;
online GT/feedback loop; Hermes delegation; WhatsApp channel; mail-evidence extraction to a
standalone shared lib.
