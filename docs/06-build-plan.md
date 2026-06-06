# 06 — Build plan

All phases are **test-driven** (failing test first) and end with a **milestone review**
(`docs/reviews/REVIEW-<date>.md` + commit list + external review + fix cycle, tagged `review-<date>`).

## Current phase

**Phase 1 — MVP + evaluation harness.** ✅ complete, and the **feedback loop is closed** (much of
what was originally "Phase 2" landed in Reviews 3–5: headless `code`/`api` reasoners, feedback
consumption, the correction mechanism, C2 billing-direction, the knowledge store). Reviews 1–5 done;
180 tests green. **Next:** first sustained **unattended `code`-backend run** (the Review-5 re-review
trigger), then Phase 1.5 (Zoom transcripts) and the J6/J7 sender mute-list.

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

## Landed after the MVP (Reviews 3–5) — was "Phase 2", now done

- **Headless model seam.** `CodeReasoner` (Claude Code `claude -p`, subscription, no API key — the
  shipped default) + provider-agnostic `ApiReasoner` (Anthropic SDK or any OpenAI-compatible/OpenRouter
  endpoint). See `docs/05`.
- **Closed feedback loop.** Feedback is consumed, not just captured: `done:`/`archive:`/`revive:`/
  `suppress:` + `forget:`/`alias:` + free-text notes → knowledge (authoritative). See `docs/04`.
- **Correction mechanism.** Reasoner + Avigail retract stale knowledge and merge mis-identified
  contacts; provenance-ranked (human > billing > model/auto) in both stores.
- **C2 billing-direction** role inference; **closure/decay**; **knowledge store**; **state-review**
  with contacts & roles, regenerated every run.

## Phase 1.5 — Zoom transcripts (near-term priority)

Wire the sibling's portable `transcripts` skill into `unify()` so transcript `EvidenceRecord`s flow
into the same packet.
*Accept:* a transcript mentioning an approval/brief updates the right project in the golden test.

## Still deferred

- **J6+J7** — one configurable, domain-keyed **sender mute-list** (replaces the hard-coded `meydata`
  denoise *and* the grow-forever per-thread `suppressed.json`).
- **J8** — close the `api`/OpenAI path with a canned-response fixture test (unit-only today).
- **J5** — cap/age the knowledge store; **J1** — optional reuse-archived-`model_output` idempotency.
- Online GT/feedback loop; Hermes delegation; WhatsApp channel; mail-evidence extraction to a
  standalone shared lib.
