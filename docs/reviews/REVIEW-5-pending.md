# Review 5 — prepared for external review

Range **`review-4..HEAD`** (tag `review-5` marks HEAD). This milestone **closes the feedback loop**: the
Review-4 fix cycle (H1–H6 + live-run L1–L3), a full **correction mechanism** (retract knowledge / merge
contacts, driven by Avigail *and* the reasoner), **C2 billing-direction**, and an always-fresh, legible
**state-review**. The closed loop was end-to-end **verified against the real model** (see below).
**175 tests green.** Nothing pushed.

## Scope — what changed, where to focus

1. **Review-4 fix cycle (verify first).** H1 (no Anthropic key to a 3rd-party endpoint — `reasoner.py`
   `select_reasoner`), H3 (`claude -p` runs in a scratch dir, scoped `--add-dir`/cwd), H4 (one
   reprompt-on-bad-JSON retry + stdout logging; openai None-content guard), H5 (default-reasoner doc),
   H6 (`is_self_generated` sender-gated; `_self_addresses` broadened). Live-run L1–L3 (suppress consumed +
   persisted; free-text feedback captured; feedback provenance `[AVIGAIL-CONFIRMED]`).

2. **Correction mechanism — the headline** (`schema.Correction`, `apply.apply_corrections`,
   `knowledge.supersede`, `contacts.set_role`/`merge`, `feedback` `# forget:`/`# alias:`,
   `reasoner` `corrections` channel). False facts no longer linger: a confirmed note (or clear evidence)
   makes the reasoner **retract** the stale knowledge note and **merge** the mis-identified contacts —
   the same channel works from Avigail's feedback. **Verified live**: given the `[AVIGAIL-CONFIRMED]`
   "Rock Design = Idan" note next to the contradicting agent note, the real `code` reasoner emitted both
   a `retract_knowledge` and a `merge_contacts` correction unprompted (archived model_output). This is the
   K2/C4/G4 cluster fully landing.

3. **Entity merge** (`ContactEntry.alias_of`, `store.merge`). Aliased addresses are physically linked to
   one canonical contact; the review surface folds them ("idandamti@ula.co.il (aka idan@rockdesign.co.il)").
   `add`/`set_role` now PRESERVE `alias_of`, so a merge survives daily re-promotion (a real bug found on
   live data — the alias was being clobbered).

4. **C2 billing-direction** (`digest_core/billing.py`). Inbound invoice → sender is a subcontractor (set
   authoritatively, rank `billing` > model/auto); outbound invoice → recipient is a payer, but only FILLS
   an unknown role (never downgrades a known agency agent to "client"); replies/forwards are skipped (a
   "Re: Invoices" ack isn't an invoice); billing mail is exempt from the N2 denoise; a fact is recorded
   ONLY when a role is set. Found+fixed two real false-positives on live data (Jen/Katie agency agents).

5. **Knowledge hygiene** (`knowledge.add_general` containment-dedup; reasoner consolidation instruction).
   Paraphrases don't pile up; the reasoner is told to retract redundant notes.

6. **State-review + operability** (`render.render_state_review_md`, `daily`, `relevance`). A
   **"Contacts & roles"** section grouped by role with humanized provenance; `daily` now **regenerates
   state-review every run** (state was always updated daily — only the snapshot was stale). meydata
   community bulletin added to the denoise.

## Commits since last review (review-4..HEAD)

```
3bfd21b Preserve alias across runs; conservative billing notes; denoise meydata
8f736be Contact alias/merge + humanized state-review reasons
7908a31 state-review fix + daily refresh + knowledge dedup/consolidation
0c08989 Review 4: mark C2 built (billing-direction) in dispositions
c11269c C2 precision fix: skip reply/forward subjects; outbound only fills unknown role (Jen/Katie fix)
9607f18 C2 billing-direction + state-review contacts
121b68e Docs: H2 fully closed (correction mechanism); RUNBOOK forget/alias
b48e8be Correction mechanism: knowledge retract + contact merge (human + reasoner)
f8596f4 Reconcile Review 4 (H1/H3/H4/H5/H6 + dispositions)
c537b91 Review 4: record live-run feedback findings L1-L3 as found+fixed
8b3a85c Fix feedback suppress + free-text + provenance
```

## Known open items / risks to probe (author-flagged — be adversarial)

- **J1 — Digest *narrative* is non-deterministic across runs.** Personal / Important-updates selection &
  phrasing come from a fresh model pass, so they vary run-to-run even on the same window (the owner hit
  this: a community bulletin appeared one run, not the next). Persistent state (projects/todos/contacts/
  knowledge) is anchored by the deterministic layer (carry-forward/decay/apply/corrections) and is stable;
  only the free-form narrative swings. *Question:* is "recall-first + suppress" enough, or do we want an
  optional reuse-cached-`model_output`-for-a-given-run-date mode for strict per-window idempotency?
- **J2 — C2 outbound on an UNKNOWN agency agent.** Outbound→client fills an unknown role; the first time a
  SPRIG agent is seen *only* via an invoice (not yet modeled as an agent), C2 would tag them `client`. The
  guard only protects an *already-known* agent. Mitigated by `billing < human` rank + the reasoner can
  correct, but flag it.
- **J3 — Billing detection is structural + reply-skip is subject-prefix based.** No morning.co/Green-Invoice
  *body* parsing (counterparty named in the body of an ESP notification is left to the model). No
  `In-Reply-To` threading.
- **J4 — Entity merge: canonical = first email in the correction (arbitrary), two rows persist by design.**
  `role_of` doesn't traverse aliases (both are set to the same role at merge time, so they agree — but a
  later single-address `set_role` could diverge them). Consider resolving `role_of` through `alias_of`.
- **J5 — Knowledge containment-dedup is heuristic** (strict substring containment — low over-merge risk,
  but semantic paraphrases still rely on the model to consolidate). K1 (unbounded growth) is mitigated, not
  capped/aged.
- **J6 — `meydata.co.il` is hard-coded in the denoise** (Avigail-specific). A configurable mute-list
  (sender domains she never wants surfaced) would be cleaner than editing code.
- **J7 — Suppressed threads persist forever** (`state/suppressed.json`); no un-suppress path except editing
  the file. Recurring-sender noise needs a sender mute, not per-thread suppression (ties to J6).
- **J8 — `ApiReasoner` OpenAI/OpenRouter path still untested against a real endpoint.** The `code` path was
  smoke-tested + one real verification run (corrections emitted correctly); the `api` path is unit-only.

## Self-caught on live data this cycle (fixed)
C2 mis-tagging Jen→client / Katie→sub (reply ack + agency agent); the entity-merge alias being clobbered by
daily re-promotion; the state-review var-shadowing bug (param `contacts` shadowed by a loop local); a
misleading "agent is invoiced by ULA" knowledge note. All fixed with regression tests.

## Findings

- [ ] <reviewer fills in> — <severity> — <resolution / commit>

## Sign-off

<reviewer> / <date>
