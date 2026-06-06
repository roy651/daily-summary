# Review 5 — external review (response to REVIEW-5-pending.md)

Reviewer response for `docs/reviews/REVIEW-5-pending.md`. Range `review-4..HEAD` (`58cfa35`-era tags now
resolve — see process note). This milestone closes the feedback loop: the Review-4 fix cycle (H1–H6 +
live-run L1–L3), a full **correction mechanism** (retract knowledge / merge contacts, driven by Avigail
*and* the reasoner), **C2 billing-direction**, entity merge/alias, and an always-fresh state-review.
Static review (sibling `mail-evidence` absent; no pytest here) — "175 green" unverified by me but
consistent; the new behaviors have matching tests, and the C2/alias/shadow fixes the author self-caught
on live data are exactly the kind of thing that should be getting caught now.

Bottom line: this is the strongest milestone of the five. The Review-4 fixes are all correct, and the
correction mechanism is well-built — with **one real asymmetry (M1): the contact store got
provenance protection, the knowledge store didn't**, so a model-sourced retract can delete or downgrade
the very `[AVIGAIL-CONFIRMED]` note this milestone exists to make authoritative. That's the one to fix
before trusting the loop unattended. Everything else is small.

## Review-4 closures — verified

- **H1** — correct. `select_reasoner` only falls back to `ANTHROPIC_API_KEY` when `provider=="anthropic"`,
  and raises loudly if an openai-compatible provider has no `LLM_API_KEY` (`reasoner.py`). The key can no
  longer reach a third-party endpoint. ✔
- **H3** — correct. `CodeReasoner` runs in a dedicated `work_dir/.reasoner` scratch dir with `cwd` and
  `--add-dir` both scoped to it, so `claude` can't reach/clobber live state (projects.json, watermarks)
  and doesn't inherit the repo's `CLAUDE.md`/skills. `--dangerously-skip-permissions` remains, but the
  writable surface is now genuinely just the scratch dir — acceptable. ✔
- **H4** — correct. One reprompt-on-bad-JSON retry with a corrective hint, stdout logged, loud raise
  after the retry; openai None-content guard. ✔
- **H6** — correct. `is_self_generated` now also requires the sender to be a self-address when
  `self_addresses` is supplied, so a real thread merely subject-named "digest:" isn't dropped. ✔
- **H2 / L1–L3** — the lynchpin is wired: feedback notes are stored `source="feedback"`, the packet calls
  `general_notes(mark_confirmed=True)` so they reach the model tagged `[AVIGAIL-CONFIRMED]`, and the
  system prompt instructs the model to treat them as authoritative and emit `corrections`. Suppress is
  consumed + persisted (`state/suppressed.json`); free-text captured. ✔ *(But see M1 — the tag says
  "authoritative" while the knowledge store will let the model delete it.)*

## Correction mechanism + C2 + entity merge — accepted, with M1

Well-designed overall: a single `apply_corrections` channel serves both Avigail (`source="feedback"`) and
the reasoner (`source="model"`), wired in the right order in `daily` (human corrections before the packet
→ billing → model corrections after the pass). The **contact store is properly guarded**: `_SOURCE_RANK`
(human > billing > model/auto), `set_role` refuses to downgrade a stronger-sourced role, `merge` links
aliases and preserves `alias_of` across daily re-promotion (the live-data clobber fix). **C2** is careful:
reply/forward subjects skipped (the Katie fix), ESP-notification counterparty deferred to the model,
billing mail exempt from N2 denoise, and outbound billing only *fills* an unknown/`other` role — a known
agent is left untouched and no false fact recorded (the Jen fix; J2's known-agent guard is real). Verified
the model schema + prompt carry the `corrections` channel.

## Findings

Severity: **Medium** = violates an intended guarantee under realistic conditions · **Low** = hardening.

- [ ] **M1 — The knowledge store has no provenance guard on removal/replacement; a model-sourced
  correction can delete or downgrade an `[AVIGAIL-CONFIRMED]` note.** — **Medium** — `knowledge.py:54-73`
  (`supersede`), `knowledge.py:32-52` (`add_general`), `daily.py:172` (model corrections, `source="model"`).
  `supersede` removes **every** note containing `match`, regardless of its source; `add_general`'s
  containment-dedup drops a shorter existing note when a longer one supersets it — neither consults
  `_SOURCE_RANK`. So the model's own `retract_knowledge` can erase a feedback/confirmed note. This bites
  even in the *verified happy path*: if the model sets `match` to the entity key ("rock design") to drop
  the stale agent note, it also nukes the confirmed "Rock Design = Idan" note (same substring), and any
  re-added note is `source="model"` — so the confirmed provenance is destroyed and, once superseded, the
  feedback note is gone permanently (feedback won't re-add it). This is the exact inverse of the H2
  guarantee, and it's asymmetric with the contact store, which *is* rank-guarded. Whether the confirmed
  note survives currently depends on the model choosing a `match` phrasing that's absent from the
  confirmed note — a model-behavior dependency the deterministic layer shouldn't rely on. *Fix:* make
  `supersede`/`add_general` never remove or replace a note whose `source` outranks the writer's (reuse
  `_SOURCE_RANK`); a model retract may purge only model/agent/auto notes. Avigail's feedback (higher rank)
  can still override anything.

- [ ] **M2 — `role_of` doesn't resolve through `alias_of` (J4), so an alias's role can go stale.** —
  **Low/Medium** — `contacts.py` `role_of`, `merge`. At merge time both addresses get the same role, so
  they agree initially — but a later authoritative `set_role` (billing/human) on the canonical doesn't
  touch the alias's stored role, and `merge` with `role=None` leaves them divergent. Downstream role
  checks that hit the alias (billing's fill-unknown gate, `promote_work_contacts`) then see the wrong
  role. *Fix:* resolve `role_of` (and role checks) through `alias_of` to the canonical entry, or propagate
  the canonical role to all aliases on every set.

- [ ] **M3 — `supersede` / `# forget:` is an unanchored substring match with no echo of what it
  removed.** — **Low** — `knowledge.py:69`. `forget: design` would drop every note containing "design".
  For a human-typed directive that's partly intended, but the blast radius is invisible. *Fix:* surface
  "retracted N notes: …" in the next digest/log (and consider anchoring to whole-note or token match).

## Author risks (J1–J8) — adjudicated

- **J1 (narrative non-determinism)** — acceptable / by-design. Persistent state is deterministic
  (carry-forward/decay/apply/corrections); only the editorial narrative swings, which is fine for the
  product. Cheap win if you want strict idempotency for re-runs/debugging: you *already* archive
  `model_output.<run_date>.json` — a "reuse the archived output for this run_date if present" mode gives
  per-window idempotency for free. Not blocking. Recall-first + suppress is enough.
- **J2** — real residual but adequately mitigated (only a first-seen agent known *solely* via an invoice
  → "client"; `billing < human` rank + reasoner correction recover it). The known-agent guard is correct. Low.
- **J3** — acceptable; ESP-notification counterparty is correctly deferred to the model. Future: parse the
  morning.co/Green-Invoice body via the sibling invoicing-assistant — but consume it through a protocol,
  never import (portability guard).
- **J4** — see M2.
- **J5** — agree; containment-dedup mitigates K1 but doesn't cap/age. Add a size/age cap eventually. Low.
- **J6 / J7** — agree, and they're the same fix: replace the hard-coded `meydata.co.il` denoise *and*
  the grow-forever per-thread `suppressed.json` with one **configurable sender mute-list** (domain-keyed,
  in state/config). Recurring-sender noise wants a sender mute, not per-thread suppression. Do them together. Low.
- **J8** — `api`/OpenAI path still unit-only. Close it cheaply with a recorded/canned-response fixture
  test (no live endpoint needed) plus the H4 guards; also shape `MODEL_OUTPUT_SCHEMA` for OpenAI strict
  mode (`additionalProperties:false` + required) if you want real json_schema enforcement there. Low.

## Process note (resolved)

Tags are now on the remote — `review-2026-06-05[b]`, `review-3`, `review-4`, `review-5` all resolve, so
every prior review range is reproducible. Fourth time was the charm; thanks for pushing them.

## Sign-off

External review 5 complete (static). **H1–H6 + L1–L3 accepted; the correction mechanism, C2, and entity
merge are sound** — strongest milestone yet. Recommend **M1** (extend `_SOURCE_RANK` protection to the
knowledge store) before relying on the closed loop unattended, since it's the inverse of the guarantee the
loop is built on; **M2/M3** and the J6/J7 mute-list consolidation are good follow-ups. Re-review after M1
and the first sustained unattended `code`-backend run.

---

## Reconciliation — dispositions (fix cycle)

All three findings fixed, test-driven (5 new tests, suite 175 → 180 green). The source-authority rank
that previously lived in `contacts.py` is now the shared `state.SOURCE_RANK` (added `agent: 0`), imported
by both stores so the contact and knowledge guards are provably the same ranking.

- **M1 — Fixed (Medium).** `knowledge.supersede` now removes a note only when the writer's source
  **outranks-or-equals** it (`SOURCE_RANK`), so a `source="model"` `retract_knowledge` can purge only
  agent/model/auto notes — never an `[AVIGAIL-CONFIRMED]` (feedback-sourced) one; Avigail's own feedback
  still overrides anything. `add_general`'s containment-dedup got the same guard: a richer model paraphrase
  no longer drops a shorter confirmed note (both are kept — the confirmed fact stands, the elaboration is
  appended). The H2 guarantee is now symmetric across both stores. Tests:
  `test_model_supersede_cannot_remove_confirmed_note`, `test_feedback_supersede_removes_even_a_confirmed_note`,
  `test_model_superset_does_not_replace_confirmed_note`.
- **M2 — Fixed (Low/Med, J4).** `contacts.role_of` resolves through `alias_of` to the canonical entry, so a
  later authoritative `set_role` on the canonical is reflected for every alias (no stale alias role).
  Test: `test_role_of_resolves_through_alias_after_canonical_set_role`.
- **M3 — Fixed (Low).** `supersede` logs `retracted N note(s): …` (logger `digest.knowledge`) so the blast
  radius of an unanchored `# forget:` is visible. Whole-note/token anchoring deferred as optional hardening.
  Test: `test_supersede_logs_removed_notes`.

**Carried forward (agreed follow-ups, not in this cycle):** J5 (cap/age the knowledge store), **J6+J7**
(one configurable, domain-keyed sender mute-list replacing the hard-coded `meydata` denoise *and* the
grow-forever per-thread `suppressed.json` — feature-sized, do together), J8 (close the `api`/OpenAI path
with a canned-response fixture + `additionalProperties:false`/required for OpenAI strict mode), and J1's
optional reuse-archived-`model_output` idempotency mode. Re-review trigger per sign-off: **post-M1 + first
sustained unattended `code`-backend run.**
