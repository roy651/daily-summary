# Review 3 — external review (response to REVIEW-3-pending.md)

Reviewer response for `docs/reviews/REVIEW-3-pending.md`. Range `582b2e7..40f0ba8` (Review-2 boundary →
HEAD): the Review-2 fix cycle (R1/K3/N1/N2/N3), entity/role-resolution work (C-series collection +
partial build), and the **D0/D1/D2 closure-decay model**. Static review again — suite not executed here
(sibling `mail-evidence` path-dep absent; no pytest in the sandbox). Verified by reading the full diff +
every new test; the "114 green" claim is consistent with the code, and each closure/decay behavior has a
dedicated test in `test_closure_decay.py`.

Bottom line: the closure/decay model is a genuine and well-built addition — it's the missing half of the
product, and the real-data numbers (22→13 active, 65→26 todos, 22 surfaced-to-confirm) are the right kind
of result. One Medium correctness risk in how the decay clock is driven (G1), one Medium feedback-closure
matching bug (G2), and three smaller items. The C-series proposals are the right priorities; my steer
below flags one concrete interaction bug-in-waiting between C2 and the new N2 denoise.

## Review-2 closures — verified

- **R1** — confirmed-column guard is now an explicit `raise RuntimeError`, not `assert`
  (`apply.py:187-195`); survives `python -O`. ✔
- **K3** — `upsert_clients` runs in `run_digest` (`daily.py:126`) and preserves existing profiles incl.
  human edits (only stubs missing ones). New post-bootstrap clients now get a profile. ✔
- **N1/N3** — indiscriminate bootstrap seeding replaced by reasoning-based `promote_work_contacts`
  (only people the model tied to real work become known/T1), with role derived from category +
  `client.is_agency` (correctly tags a SPRIG manager on SPRIG-direct work as *agent*, the Katie lesson).
  Contact roles now carry a `source` + a sticky-precedence rule (`contacts.add:70-76`). ✔ *(See G4.)*
- **N2** — `partition_marketing` is exactly the conservative shape recommended: structural signals only
  (`no-reply`/ESP-domain/`is_bulk`), drops a thread only if **every** record is marketing (one human
  reply keeps it), explicitly **not** language-keyed, and the dropped set is surfaced (`filtered`). ✔

K1 (uncapped knowledge in packet) and K2 (knowledge provenance / human-confirmed tier) remain open as
previously agreed — K2 is now load-bearing for C2/C4 (see steer). Not regressions.

## D0/D1/D2 closure-decay build — accepted, with G1

The model is sound in shape: three closure inputs + a never-delete safety valve, all surfaced for
confirmation. Verified: evidence-based `closed_todos` (exact `_norm_text`, `apply.py:125-133`); model
`status: done` drops from active; feedback check-off consume runs **first** in `run_digest`
(`daily.py:84-102`); passive decay via `suspected_closures` with the "overdue ⇒ suspected-done only if the
project is *also* stale" refinement (`todos.py:209-235`); reversible billed auto-archive + revive
(`auto_archive_billed`, `apply.py:114-120`). **D1 is genuinely fixed** — overdue no longer inverts to max
urgency; `_score` branches on `days_to_due < 0` to a flat +6 nudge (`todos.py:72-80`), tested by
`test_overdue_deadline_not_urgent`. Good coverage across `test_closure_decay.py` (14 cases).

## New findings

Severity: **Medium** = wrong/degraded output under realistic conditions · **Low** = hardening/edge.

- [ ] **G1 — Decay + billed auto-archive silently depend on the model NOT re-stating unchanged
  projects; nothing deterministic or tested enforces it.** — **Medium** — `apply.py:138-147`,
  `daily.py:109-135`. The `last_activity_date` floor sets the date to `run_date` for *any* project the
  model emits an update for when there's no fresher evidence date (the `elif` at `:146`). But the packet
  feeds **every** open project (`current_projects`), so a model that re-states them — a common, reasonable
  behavior — resets every dormancy clock each run. `suspected_closures` (dormant ≥28d) and
  `auto_archive_billed` (silent ≥7d) then **never fire**. It works *today* (the real run surfaced 22
  suspects, so the current in-session model is disciplined), but this is an undocumented, untested
  coupling between a deterministic feature and model-output discipline — exactly the kind of hidden
  dependency the architecture otherwise avoids — and a landmine for the headless `ApiReasoner` (no prompt
  contract exists yet). It also erodes the Review-1 "last_activity from evidence, never from the model"
  invariant; the `apply.py` module docstring (`:7`) now misstates it. *Fix:* gate the floor on *real* new
  evidence — `_max_evidence_date(update.evidence_thread_ids, thread_dates)` for *this* update — not on the
  mere presence of an update; add a regression test (an echoed-unchanged project must age, not reset);
  document the "only update projects with new window evidence" contract for the future API prompt; correct
  the docstring.

- [ ] **G2 — Feedback todo-closure matches by substring, so checking one todo can silently close
  another — and it's less precise than the model path.** — **Medium** — `todos.py:239-259`,
  `feedback.py:53-67`. `close_todos_from_feedback` does `todo.text.lower() in checked_line`; when one
  todo's text is a substring of another's ("Send the brochure" vs "Send the brochure to Acme"), checking
  the longer silently removes the shorter. That's a silent loss of an open item — the precise failure
  "surface, don't drop" is meant to prevent — and it's inconsistent with the model `closed_todos` path,
  which uses exact `_norm_text`. The robust key (the `<!-- project_id/task_id -->` marker) is parsed off
  and **discarded** by `_clean`. *Fix:* key feedback closure on the marker (or exact normalized text of
  the parsed todo portion), matching the model path. The human's explicit check-off should be the *most*
  precise closure signal, not the fuzziest.

- [ ] **G3 — Revival of an auto-archived project relies on apply's match heuristics; a miss creates a
  duplicate active project.** — **Low/Medium** — `apply.py:114-120`, `packet.py` (done/archived dropped).
  Archived/done projects aren't in the packet, so the model can't echo their id; revival only happens if
  `_find_match` reconnects a new update by shared-evidence-thread or exact normalized title. A continuation
  with a fresh thread id and a slightly different title creates a *duplicate* active project while the
  archived original stays hidden. *Fix:* when a would-be-new project exact-title/same-client (or
  shared-thread) matches an **archived** one, prefer revive; and/or surface "revived / possible duplicate"
  in the confirm section so the human catches it.

- [ ] **G4 — Sticky contact roles harden a wrong first-pass role inference (reinforces C1/C2).** —
  **Low** — `contacts.add:70-76`. Making the first non-"other" role sticky against later inferred sources
  is good for run-to-run stability, but it means a wrong early model role (the exact C1 failure: Lee as
  client, Katie as client) can never be self-corrected by the model — only a human edit fixes it. This
  *raises* the stakes on C1/C2: there must be (a) a human role-override path, and (b) a higher-authority
  signal (billing direction, C2) allowed to override a prior model guess. Tie the precedence to provenance
  (K2), not just to "first writer wins".

- [ ] **G5 — `auto_archive_billed` only considers `status == "active"`.** — **Low** — `todos.py:271`. A
  fully-billed project parked in `on_hold`/`blocked` won't auto-archive and could linger. Probably the
  intended conservative scope; confirm it's deliberate (a billed `on_hold` project is plausibly also
  done).

## Steer on the C-series (proposals — not yet built)

- **C1 (entity/role resolution)** — agree it's the weakest reasoning step, and G4 makes it more urgent
  (mistakes are now sticky). Endorse the explicit "entity & role resolution" prompt step + reasoning-by-
  analogy to known roles. But the highest-leverage lever is C2, so sequence C2 first.
- **C2 (billing direction) — strongly agree; highest-leverage precision fix.** It's a near-deterministic
  signal (outbound invoice → recipient is a client; inbound invoice → sender is a sub) and it would have
  typed Lee and Katie correctly. **Concrete interaction bug-in-waiting:** the very signal C2 needs —
  invoice notices from morning.co/Green Invoice and ESP senders — is exactly what the new N2
  `partition_marketing` will demote (no-reply/ESP-domain). **C2 must add a billing-sender allowlist/override
  to `partition_marketing` (and to any future bulk drop) so invoice mail is never denoised away.** Persist
  the result as relational knowledge with provenance that **outranks** a model role-guess (so it can
  override the sticky role in G4) — this is the K2 tier. And reuse the sibling invoicing-assistant's
  existing morning.co parsing rather than re-parsing — but consume it through a protocol, never import it
  (the portability guard).
- **C3 (surface new entities for confirmation) — strongly agree; cheap, high-value.** It's the systematic
  version of how the human caught Lee/Katie, and `render` already has the "confirm to clear" pattern to
  mirror. A "New entities this run — confirm role" section (entity + inferred role + one-line basis) pairs
  naturally with the decay confirm section. Do this alongside C2.
- **C4 (interaction surface)** — agree it's the right next investment after C2/C3. The consume-half
  (route feedback notes → `knowledge.json` / client `observations` / **role overrides** with
  human-confirmed provenance) *is* the K2 learning loop and must carry the provenance tier so confirmed
  facts outrank agent guesses (and unstick G4). On-demand PDF/email report is low-risk additive (the `pdf`
  skill exists). Suggested order: **C2 → C3 → C4-consume**, with K2 provenance threaded through C2 and C4.

## Process note (third time)

There are still **no git tags**. The notes' diff ranges (`review-2026-06-05..HEAD`, `582b2e7..HEAD`)
reference tags that don't exist, so they aren't reproducible by a third party. Recommend tagging the
reviewed commits (`review-2026-06-05`, `-b`, and this one `-c`/`review-3`) per the `reviews/README.md`
process so future ranges are unambiguous.

## Reconciliation — dispositions (owner-side, 2026-06-05)

Tagged `review-3` at `40f0ba8` (tags `review-2026-06-05`, `-b` already existed — process note now closed).

- **G1 (decay clock resets if model re-states an unchanged project)** — **AGREE, fix before headless.**
  The `run_date` floor fires on the mere presence of an update, so a re-stating model resets every
  dormancy clock. *Does not bite the first SUPERVISED draft* (in-session authoring only emits updates for
  projects with genuine new-window evidence — the reviewer's own observation that the live model is
  disciplined), but it's a silent landmine for `ApiReasoner`. Fix: advance `last_activity_date` only from
  evidence in *this run's window cited by this update* (`update.evidence_thread_ids ∩ thread_dates`); drop
  the presence-of-update floor; add a regression test (echoed-unchanged project must age); correct the
  `apply.py` docstring. **Scheduled: do alongside the run-to-today, before any unattended/API run.**
- **G2 (feedback substring closure can clear the wrong todo)** — **AGREE, fix before headless.** Note the
  rendered marker is *project-level* (`<!-- project_id[/task_id] -->`), so it can't disambiguate two todos
  in one project — the robust key is exact normalized match on the parsed todo *text portion* (mirroring
  the model `closed_todos` path), not the marker alone. Affects Avigail's check-off interaction, not draft
  generation. **Scheduled with G1.**
- **G3 (revival → duplicate active project)** — DEFER (Low/Med). Surfaces as a visible duplicate the human
  catches; fold into C3's "new entities / revived — confirm" section when C3 is built.
- **G4 (sticky roles harden a wrong first-pass role)** — DEFER, tie to C2/K2. The fix is provenance-tiered
  precedence (billing-direction + human override outrank a model guess), which *is* C2 + the K2 tier. Not a
  standalone change.
- **G5 (`auto_archive_billed` only `active`)** — CONFIRMED DELIBERATE (conservative). A billed `on_hold`/
  `blocked` project isn't auto-archived; it still surfaces via passive decay. Left as-is.
- **C-series** — ACCEPT the sequence **C2 → C3 → C4**, with the C2/N2 denoise-exemption (never demote
  invoice senders) and K2 provenance folded in from the start. These are *precision/UX*, post-first-draft;
  not MVP blockers (the supervised review loop — Avigail as reviewer — absorbs role mistakes; C3 makes that
  systematic rather than luck-based).

**MVP verdict:** supervised MVP is complete — no major gaps. G1/G2 are the only must-fix before flipping to
unattended/`ApiReasoner`; both small. Next concrete step: bring state current (replay the 05-19→06-03 gap)
to produce Avigail's first real draft.

## Sign-off

External review 3 complete (static). **Review-2 closures accepted; D0/D1/D2 closure-decay build accepted.**
Recommend addressing **G1** (gate the decay clock on real evidence) and **G2** (marker-keyed feedback
closure) before relying on decay/auto-archive unattended or wiring `ApiReasoner` — both are small, and G1
in particular will otherwise fail silently under a different model/prompt. **G3/G4/G5** are follow-ups.
On the pending C-series: proceed **C2 → C3 → C4**, and fold the C2/N2 denoise-exemption + K2 provenance in
from the start. Re-review after the first live IMAP pull and the C2 build.
