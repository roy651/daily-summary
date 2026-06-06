# Review 4 — external review (response to REVIEW-4-pending.md)

Reviewer response for `docs/reviews/REVIEW-4-pending.md`. Range `review-3..HEAD` (commits `58cfa35..c7d5a9b`).
This milestone is large: the G1/G2 fix cycle + four reasoner backends, multi-account live pull, a single
`--dry-run` knob, and a closed feedback loop. Static review again (sibling `mail-evidence` path-dep
absent; no pytest in the sandbox) — "147 green" is unverified by me but consistent with the diff; the
new behaviors have matching tests. The author flagged R-A…R-H and asked for adversarial probing there —
done below.

Bottom line: the Review-3 fixes are correct, and the architecture held up well under a big expansion. The
real exposure is in the new headless/cloud surface: one credential-leak footgun (H1), the feedback
"provenance" that doesn't actually reach the reasoner (H2, = K2 still open), and operability gaps around
the `claude -p` handshake and JSON robustness (H3/H4). None are deep design faults; all are contained
fixes. I'd land H1/H2 before trusting the headless path unattended.

## Review-3 closures — verified

- **G1** — correct. `last_activity_date` now advances only from `_max_evidence_date(update.evidence_thread_ids,
  thread_dates)` — evidence cited by *this* update that falls in *this* run's window — and the old
  "floor to run_date on any update" `elif` is gone (`apply.py:141-145`). A re-stating model no longer
  resets the dormancy/auto-archive clock; the Review-1 "last_activity from evidence, never from the model"
  invariant is restored and the activity contract is documented in `_REASONER_SYSTEM`. Regression tests
  present (`test_restated_project_without_new_evidence_does_not_reset_clock`). ✔
- **G2** — correct, and the round-trip holds: `close_todos_from_feedback` matches on exact
  `_rendered_todo_key`, which reconstructs the rendered line body and equals `render_todos_md`'s line
  (`_client_label` matches; `_norm_text` absorbs the double-space), so checking a sibling no longer closes
  a substring todo. ✔
- **Leak fix** — `prioritize` skips `done`/`archived` projects (`todos.py:108`), so closed-project todos
  don't resurface. ✔

G3/G4/G5 dispositions were recorded in `58cfa35` (not re-audited line-by-line); note that **G4 is
effectively still open** and now load-bearing — see H2.

## New surface — assessment + author-risk adjudication

The four-backend seam is clean (one `Reasoner` protocol, shared `_REASONER_SYSTEM` + `MODEL_OUTPUT_SCHEMA`,
`_consume_output` factored out and reused — single-use archive + packet delete preserved; `CodeReasoner`
unlinks a stale output before running, so the F1 footgun stays closed). `schema.py` remains the
authoritative gate and re-validates loudly, so a loose JSON schema can't smuggle a bad enum past apply.
Multi-account pull keeps a per-account watermark and committing only after delivery. Good.

Author-flagged risks:

| Risk | Verdict |
|---|---|
| **R-A** CodeReasoner live path untested | Real — see **H4** (no repair/retry; file-handshake is fine, but harden it). |
| **R-B** OpenAI/OpenRouter path untested | Real — see **H4** (strict-schema gap + None-content crash). |
| **R-C** `--dangerously-skip-permissions` | Real — see **H3** (scope `--add-dir` away from live state; neutral cwd). |
| **R-D** heuristic reply / `is_self_generated` broadening | Low — see **H6** (subject-only false-drop; cheap sender tightening). |
| **R-E** entity correction advisory only | Real — folded into **H2** (no role override / alias; stays stuck). |
| **R-F** FileDelivery no-op + always-write out/ | **Fine.** `run_digest` writes `out/digest_<date>.md` + `out/todos.md` itself (`daily.py:154-156`); no output is lost. Name is slightly misleading; consider renaming the backend `NoSendDelivery`. |
| **R-G** unbounded knowledge growth (K1) | Still open, and slightly worse: feedback notes append the whole `freeform_notes` blob as one general note with text-dedup only. Cap/age as previously recommended. |
| **R-H** two decoupled windows | Low / by-design. The model sees all pulled threads; the highlight window is cosmetic. One real edge under `session`+live-pull: a second (resolve) run re-pulls and advances the watermark past mail the already-authored output never saw — minor, and not applicable to the headless `code` path where the pass is synchronous. |

## Findings

Severity: **Medium** = wrong output / security / fails-unattended under realistic conditions · **Low** = hardening.

- [ ] **H1 — `ApiReasoner` can send the Anthropic key to a third-party endpoint.** — **Medium
  (secret hygiene)** — `reasoner.py:444`. `select_reasoner` sets
  `api_key = env["LLM_API_KEY"] or os.environ["ANTHROPIC_API_KEY"]` *regardless of provider*. With
  `LLM_PROVIDER=openai` + `LLM_BASE_URL=<openrouter/together/local>` and `LLM_API_KEY` unset, the
  Anthropic key is handed to `openai.OpenAI(api_key=…, base_url=…)` and transmitted to that third party on
  every call. *Fix:* only fall back to `ANTHROPIC_API_KEY` when `provider == "anthropic"`; for
  openai-compatible, require `LLM_API_KEY` and fail loudly if missing. (Also: this branch reads
  `os.environ` directly instead of the injected `env` — minor inconsistency, align it.)

- [ ] **H2 — Feedback "provenance" never reaches the reasoner, so human corrections don't actually
  outrank agent guesses (K2 still open; the note's claim is not realized).** — **Medium** —
  `knowledge.py:36`, `daily.py:107-109`, `packet.py:146`. Free-text feedback is stored with
  `source="feedback"`, but `general_notes()` returns bare `o.note` and the packet's `knowledge` array is
  plain text — the `source` is dropped. So a human correction ("Rock Design = Idan, a sub") and an agent
  guess ("Rock Design is a client") appear as equal-weight notes; on conflict the model has no signal
  which to trust. Worse, the correction lands *only* as advisory text — it does not update the sticky
  contact role (Review-3 G4) or create an alias (R-E), so the wrong role stays stuck regardless. *Fix:*
  surface provenance to the model — a separate authoritative `confirmed_facts` block the system prompt
  says to treat as overriding, or a per-note tag — and let a confirmed entity/role correction mechanically
  override the contact store (the consume-half of K2 that C4 was meant to deliver). This is the gap that
  makes the whole feedback loop "advisory" rather than "closed."

- [ ] **H3 — CodeReasoner runs `claude -p` with `--dangerously-skip-permissions`, `--add-dir <state>`,
  and the repo cwd.** — **Medium (security/operability)** — `reasoner.py:297-307`. The real containment
  is `--allowedTools Read,Write` (no Bash/exec) — good — but (a) the global skip-permissions flag in an
  unattended cron is the pattern Anthropic warns against, and `--add-dir <state_dir>` makes the *whole
  state dir* (projects.json, clients.json, watermarks) writable, so a confused agent could clobber state
  via the Write tool; scope the handshake to a dedicated scratch dir (packet + output only) and prefer a
  settings-scoped permission mode over the blanket flag. (b) `claude` inherits the repo cwd, so it
  auto-loads *this repo's* `CLAUDE.md` + skills into the reasoning context — dev conventions irrelevant to
  (and potentially distracting from) the business-reasoning task; run it from a neutral working directory.

- [ ] **H4 — No JSON repair/retry on either headless backend: one malformed output = no digest that
  day.** — **Medium (operability)** — `reasoner.py:282-287, 392-414`. `CodeReasoner` hard-fails if
  `claude` writes prose / a code fence / to the wrong path (`_consume_output`'s `json.loads` raises; the
  captured stdout that might explain it is discarded on the success path). `ApiReasoner(openai)` does
  `json.loads(resp.choices[0].message.content)` assuming content is present and valid — a tool-call or
  refusal yields `None` → crash — and `MODEL_OUTPUT_SCHEMA` isn't OpenAI strict-mode shaped
  (`additionalProperties:false` + every key in `required`), so json_schema enforcement varies by provider.
  For an unattended daily job, add: always log `claude` stdout, one reprompt-on-invalid-JSON retry, and a
  None/empty-content guard. On R-A's question — the file handshake is the right choice (more deterministic
  than parsing prose out of `--output-format json`'s envelope); just make it robust.

- [ ] **H5 — Default-reasoner mismatch between the note and the code.** — **Low** — `reasoner.py:424`.
  The note calls `code` the default; `select_reasoner` defaults to `session`. `session` is the safer
  default (don't auto-shell-out unless asked) — confirm intent and make the note + `.env.example` agree.

- [ ] **H6 — `is_self_generated` is subject-only (R-D).** — **Low** — `relevance.py:29-36`. After
  stripping `Re:/Fwd:`, any thread whose subject starts with `digest:` is dropped as self-generated — a
  real client thread named that way would be wrongly excluded (recall-is-the-gate violation, low
  probability). *Fix:* also require the sender to be our SMTP user / Avigail. The reply detector is
  heuristic (no `In-Reply-To`/`Message-ID`); fine for v1, but persist the sent `Message-ID` so a future
  version can thread replies precisely rather than by subject substring.

## Steer

Priority order: **H1** (one-line, prevents a key leak) and **H2** (turns the "closed" loop from advisory
into actually-authoritative — it's the K2/C4/G4 cluster converging) before the headless path is trusted
unattended; then **H3/H4** to make `code`/`api` cron-safe; **H5/H6** are quick cleanups. On the C-series:
**C2 (billing direction)** remains the highest-leverage unbuilt precision fix and pairs naturally with H2
(billing-direction is exactly the kind of high-confidence relational fact that should enter the
authoritative tier and override a sticky role) — and remember the C2/N2 denoise-exemption I flagged in
Review 3 (invoice/ESP mail must not be demoted). **C3** is partially there via `kind:entity`; a
deterministic "new entities this run" diff would still be more reliable than relying on the model to
self-flag.

## Process note (fourth time)

Still **no tags on the remote** — `git tag` is empty despite `58cfa35`'s "tag review-3" (local tags
aren't pushed by default; "Nothing pushed" in the note confirms it). The diff ranges in every review note
(`review-3..HEAD`, the `review-4` tag) therefore don't resolve for anyone else. `git push --tags` for
`review-3` and `review-4` would make all four ranges reproducible.

## Reconciliation — dispositions (owner-side, 2026-06-06)

- **H1 (key leak) — FIXED.** `select_reasoner` now falls back to `ANTHROPIC_API_KEY` ONLY for
  `provider=anthropic`; an openai-compatible provider requires its own `LLM_API_KEY` and fails loudly if
  missing, so the Anthropic key is never handed to a third-party endpoint. Reads the injected `env`, not
  `os.environ`. Test: `test_select_reasoner_never_leaks_anthropic_key_to_third_party`.
- **H2 (provenance) — FIXED (`8b3a85c` + `b48e8be`).** Two parts: (1) feedback notes are tagged
  `[AVIGAIL-CONFIRMED]` in the packet and the reasoner is told to follow them over its own inference and
  older notes (the "surface provenance" fix). (2) The *mechanical* half — a full **correction mechanism**:
  `knowledge.supersede` (retract a false note, optionally replace) + `contacts.set_role` (force a role;
  human outranks model) applied via `apply_corrections`, driven by BOTH Avigail's feedback
  (`# forget:` / `# alias:` in the todos file, `forget:` / `alias:` in an email reply) AND the reasoner's
  own `corrections` channel in `ModelOutput`. The reasoner is now instructed to RECONCILE — retract the
  stale note + merge the aliased contacts — rather than append a contradicting note (the Idan/Rock-Design
  case). This also closes **R-E** and the **G4** sticky-role cluster (a confirmed correction overrides the
  sticky role). Tests: `test_corrections.py`. **Remaining (smaller):** the merge sets the same role on all
  aliased addresses + records the alias as knowledge; it does not physically collapse the rows into one
  canonical contact (cosmetic). Pairs with **C2** as the reviewer noted.
- **H3 (claude -p sandbox) — FIXED.** `CodeReasoner` now uses a dedicated scratch dir (`state/.reasoner/`,
  packet + output only); `claude` runs with `cwd` + `--add-dir` scoped to it, so it can't reach live state
  (projects.json, watermarks) and doesn't auto-load this repo's `CLAUDE.md`/skills. Tools stay
  `Read,Write`. (`--dangerously-skip-permissions` retained, but blast radius is now the scratch dir; a
  settings-scoped permission mode is a later refinement.)
- **H4 (JSON robustness) — FIXED.** `CodeReasoner` does one reprompt-on-invalid/missing-JSON retry and
  logs claude's stdout (debug) instead of discarding it; `ApiReasoner(openai)` guards empty/None content
  with a clear error. *Deliberately NOT done:* reshaping `MODEL_OUTPUT_SCHEMA` to OpenAI strict-mode
  (every key required + `additionalProperties:false`) — we keep it permissive and rely on `schema.py` as
  the authoritative gate; the retry + None-guard cover the failure modes.
- **H5 (default mismatch) — FIXED (docs).** Clarified that `session` is the safe built-in default and
  `code` is selected by this deployment's `.env` (`.env.example` + a `select_reasoner` comment now agree).
- **H6 (self-generated subject-only) — FIXED.** `is_self_generated` now also requires the sender to be
  one of Avigail's addresses when `self_addresses` is supplied; `_self_addresses` was broadened to all of
  them (per-account IMAP users + `SMTP_USER` + `DIGEST_EMAIL_TO`) so the outbound digest is still
  recognized while a client thread named `digest:` is not dropped. `unify` passes them through. Tests in
  `test_email_feedback.py`. *Open:* persisting the sent `Message-ID` for precise `In-Reply-To` threading
  (vs subject heuristic) — noted for a later pass.
- **Process / tags.** `review-3` and `review-4` tags exist locally; pushing remains the owner's gate
  (will `git push --tags` on request).
- **C-series.** **C2 (billing-direction) — BUILT** (`digest_core/billing.py`): detect invoices/receipts
  (incl. Hebrew + morning.co/Green-Invoice senders), infer role from direction (inbound→subcontractor
  set authoritatively; outbound→client only FILLS an unknown role so it never downgrades an agency
  agent), record relational knowledge, and exempt billing mail from the N2 denoise. Contact precedence
  is now rank-based (human > billing > model/auto). Found+fixed a real false-positive on live data (a
  "Re: Invoices" reply / invoicing a SPRIG agent — see commit c11269c). C3 partially covered by
  `kind:entity`; a deterministic new-entity diff is still the more reliable option (carried forward).

**Net:** H1/H3/H4/H5/H6 fixed (154 tests green); H2 core fixed, its mechanical-override half scheduled.
Recommend doing the H2 alias/role-override + C2 before the next unattended-`code` milestone.

## Sign-off

External review 4 complete (static). **G1/G2 + leak fixes accepted; the backend/multi-account/feedback
expansion is sound in architecture.** Recommend **H1** and **H2** before relying on the headless,
self-delivering path unattended, and **H3/H4** before wiring `code`/`api` into cron. Re-review after the
first unattended `code`-backend live run and the C2 build.
