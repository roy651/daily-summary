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

## Sign-off

External review 4 complete (static). **G1/G2 + leak fixes accepted; the backend/multi-account/feedback
expansion is sound in architecture.** Recommend **H1** and **H2** before relying on the headless,
self-delivering path unattended, and **H3/H4** before wiring `code`/`api` into cron. Re-review after the
first unattended `code`-backend live run and the C2 build.
