# Review 4 — prepared for external review

Range **`review-3..HEAD`** (tag `review-4` marks HEAD). This milestone took the system from
"supervised, file-output MVP" to a **headless, multi-account, self-delivering daily digest with a
closed feedback loop**, plus the Review-3 fix cycle. **147 tests green.** Nothing pushed.

## Scope — what changed and where to focus

1. **Review-3 fix cycle (G1/G2 + a leak found during the live backfill).** Verify these first.
   - **G1** — `last_activity_date` now advances ONLY from evidence in *this run's window cited by this
     update* (`apply.py` `_apply_one`, `_max_evidence_date(update.evidence_thread_ids, thread_dates)`);
     the old "floor to run_date on any update" is gone, so a re-stating model can't reset the decay
     clock. Activity-contract documented in the packet glossary (`packet.py`). Regression tests in
     `test_closure_decay.py` (`test_restated_project_without_new_evidence_does_not_reset_clock`,
     `test_new_window_evidence_advances_last_activity`) + updated `test_apply.py`.
   - **G2** — feedback todo-closure is now EXACT normalized rendered-line match, not substring
     (`todos.py` `_rendered_todo_key` / `close_todos_from_feedback`); `test_feedback_closure_is_exact_not_substring`.
   - **Leak** — `prioritize()` skips `done`/`archived` projects so closed-project todos don't resurface
     (`todos.py`); `test_archived_or_done_project_todos_not_ranked`.

2. **Reasoner backends — the big one** (`reasoner.py`, `test_reasoner_backends.py`). The seam now has
   four interchangeable implementations behind one `Reasoner` protocol, selected by `REASONER`:
   - `session` (supervised, existing), `replay` (tests, existing).
   - **`code`** (new, default) — headless **Claude Code** (`claude -p`) on the user's subscription, no
     API key. Writes the packet, shells out, validates + single-use-consumes the output.
   - **`api`** (new) — **provider-agnostic**: `LLM_PROVIDER=anthropic` (Anthropic SDK, tool-forced) or
     `openai` (any OpenAI-compatible endpoint, e.g. OpenRouter, via `LLM_BASE_URL`/`LLM_MODEL`/`LLM_API_KEY`).
   - Shared contract `_REASONER_SYSTEM` + `MODEL_OUTPUT_SCHEMA` (JSON Schema for the structured output),
     reused by both cloud-ish backends so swapping providers is an env change. `_consume_output` factored
     out of `SessionReasoner` and reused by `CodeReasoner` (single-use archive + packet delete preserved).

3. **Multi-account live pull** (`cli.py` `_live_pull`). Iterates `IMAP_ACCOUNTS` (ula + gmail), each with
   its own watermark and its own inbox/sent folders (fixes Gmail `[Gmail]/Sent Mail` vs the generic
   `Sent`), logs each account before pulling. Read-only EXAMINE invariant unchanged.

4. **CLI / operability** (`cli.py`, `delivery.py`, `daily.py`).
   - **Single `--dry-run` knob** — `DRY_RUN` env removed. `run_digest` now ALWAYS writes `out/` artifacts
     (so a dry-run is readable); `--dry-run` skips send + persist + watermark only. `FileDelivery.deliver`
     is now a no-op (pipeline owns artifacts); `select_delivery(..., dry_run=)` from the flag.
   - **Auto digest window** (`_digest_window_since`) — ≥2 days, extends back to the oldest watermark,
     warns (proceeds) if span > 1 month; `--since` / `--window-days` prescribe (backlog / re-bootstrap).
   - **`.env` auto-loaded** via python-dotenv in `main()` (never `source` it); shell env still overrides.

5. **Feedback loop closed** (`delivery.py`, `feedback.py`, `daily.py`, `relevance.py`).
   - **Email-reply collection** — `EmailDelivery.collect_feedback(threads=…)` finds Avigail's reply
     among the pulled threads (from her address, `digest:` tag, not the outbound itself), strips the
     quoted original (`_strip_quoted`, EN + Hebrew markers), parses directives.
   - **Notes → knowledge** — free-text feedback is appended to the knowledge store (provenance
     `feedback`) so corrections reach the reasoner next run and outrank its guesses (e.g. the Rock
     Design = Idan entity fix). `test_feedback_consume.py`.
   - Her reply is kept OUT of the reasoner's evidence: `is_self_generated` now strips a leading
     `Re:/Fwd:` so `Re: digest:` is recognized (`relevance.py`).

6. **Digest sections + feedback template** (`schema.py`, `render.py`, `reasoner.py`).
   - `Unresolved.kind` ∈ {unplaced, personal, lead, entity}; render splits into **Personal /
     Possible new leads / New people & roles — confirm / Needs your eye**. Reasoner instructed to set kind.
   - `out/todos.md` ends with a parse-safe **feedback template** (`# archive:`/`# revive:`/`# suppress:`/
     `# notes:` placeholders, empty = no-op, regenerated each run). `test_render_sections.py`.

## Commits since last review (review-3..HEAD)

```
c7d5a9b Personal/entity sections + todos feedback template
9be44d2 Docs: feedback is consumed (file + email); RUNBOOK on how Avigail corrects entities
b15b07b Email feedback collection
7236499 Feedback: route Avigail's free-text notes into the knowledge store (provenance=feedback)
7e22e06 dry-run unification + auto window + quiet reasoner
febb511 Live pull: log each account being pulled; pass per-account inbox/sent folders to fetch (Gmail Sent)
ef44dce CLI auto-loads ./.env via python-dotenv (never source it); RUNBOOK drops the source line; quote .env
653cab8 Docs: RUNBOOK on-demand/headless run sequence + REASONER backends; refresh .env.example
ea5a226 Reasoner backends + multi-account live pull
79e8318 prioritize: skip done/archived projects so closed-project todos don't resurface as active work
7ee9c34 Fix G1 (decay clock) + G2 (exact-match feedback closure); document model activity contract
58cfa35 Reconcile Review 3: dispositions for G1-G5 + C-series; tag review-3
```

## Known open items / risks to probe (author-flagged — be adversarial here)

- **R-A — `CodeReasoner` live path is unverified by tests.** Unit tests inject the runner; the real
  `claude -p` subprocess (flag set, 15-min timeout, subscription auth, the fact that it auto-loads THIS
  repo's `CLAUDE.md`/skills, and whether it reliably writes valid JSON to `model_output.json`) is only
  exercised by the owner's live run. No structured-output guarantee from Claude Code (vs the API's
  tool-forcing). *Question:* is the file-handshake (`claude` writes the file, we validate) robust enough,
  or should we use `--output-format json` and capture stdout instead?
- **R-B — `ApiReasoner` OpenAI/OpenRouter path untested against a real endpoint.** `response_format`
  `json_schema` support and strictness vary by provider; no retry/repair on malformed JSON.
- **R-C — `--dangerously-skip-permissions`** in `CodeReasoner._default_runner`. Blast radius is limited
  (`--allowedTools Read,Write`, `--add-dir <state>`), but please sanity-check.
- **R-D — Email-reply detection is heuristic**, not RFC threading: from-address substring + `digest:` in
  subject + "not starts-with tag". No `In-Reply-To`/`Message-ID` match. And the `is_self_generated`
  broadening (strip `Re:/Fwd:`, then prefix match) will drop ANY mail whose de-prefixed subject starts
  with `digest:` — confirm that can't false-drop a real client thread. Top-posting assumed by `_strip_quoted`.
- **R-E — Entity correction is advisory only.** Notes land in `knowledge.json`; no mechanical contact
  dedup/alias (e.g. `idandamti@ula.co.il` vs `idan@rockdesign.co.il` stay two rows). Proposed next:
  an `# alias:` directive. Relates to reviewer **C1/N3**.
- **R-F — `FileDelivery` is now a no-op sender** and `run_digest` writes `out/` unconditionally (even on
  `--dry-run`). Confirm the contract is clear (the name is now slightly misleading) and that writing
  artifacts during a dry-run is acceptable.
- **R-G — Knowledge growth unbounded (reviewer K1, still open)** — feedback notes now also append with no
  dedup/cap; the packet includes `knowledge_general`. Could bloat the prompt over time.
- **R-H — Two windows, decoupled by design** — ingest is watermark-driven; the digest highlight window
  is `_digest_window_since`. Confirm they stay coherent under `--since` backlog loads and skipped runs.

## Cross-refs to the reviewer's C-series (Review 3)

- **C2** (billing-direction parsing) — still **manual**; the owner's run captured it as insights by hand.
- **C3** (surface new entities for confirmation) — **partially built** as the model-driven
  `kind: entity` → "New people & roles — confirm" section (not a deterministic new-entity diff).
- **C4** (consume feedback into state/knowledge) — **substantially built** (file + email, notes→knowledge).

## Live-run findings (owner-found in the first file-delivery run; FIXED — commit 8b3a85c)

The first real `DELIVERY=file daily` run ignored both feedback items. Root causes + fixes:
- **L1 — `# suppress:` was parsed but never applied.** `feedback.suppressed_threads` was populated and
  dropped on the floor; nothing filtered the thread, so a flagged-off spam lead kept surfacing. *Fix:*
  `run_digest` now persists a `state/suppressed.json` set, unions new suppressions, and filters those
  thread-ids out of `cleaned` before the packet — so suppressed threads never reach the reasoner, this
  run or later. Test: `test_suppressed_thread_is_filtered_and_persisted`.
- **L2 — free-text corrections were silently dropped.** `parse_todos_md` only captured a note from a
  line starting exactly with `# notes:`; any other prose (her actual sentence) vanished with no error.
  *Fix:* once past the `## ✎ Feedback` heading, plain prose is captured as a note (help `<!-- -->`
  comment skipped; `# note:` singular accepted). Tests in `test_feedback_parse.py`.
- **L3 — feedback notes had no authority over the model's own guesses.** Knowledge entered the packet
  as a flat list; the model even re-asserted the contradicted belief as a fresh agent insight. *Fix:*
  feedback-sourced notes are tagged `[AVIGAIL-CONFIRMED]` in the packet and the reasoner is instructed
  to follow them over its inference and over older contradicting notes (`knowledge.general_notes(mark_confirmed=True)`).
  **Still open:** the stale contradicting *agent* note isn't removed — it's only overridden by authority
  marking; and entity dedupe is still advisory (see R-E). A feedback directive that supersedes/removes a
  specific knowledge note is a candidate next step.

## Findings

- [ ] <reviewer fills in> — <severity> — <resolution / commit>

## Sign-off

<reviewer> / <date>
