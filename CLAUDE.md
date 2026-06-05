# CLAUDE.md

Always-on context for Claude Code. Keep this file lean — it is loaded every turn.
Heavy detail lives in `docs/`; pull in the one doc a task points to.

## Mission

Read Avigail's (freelance design studio **ula**) daily correspondence and produce a short
**morning digest**: (1) status of her ongoing projects, (2) the important updates from the last
~24h, and (3) a **prioritized TODO list** for the next day or two. It must *reason*, not
concatenate. Sibling product to `invoicing-assistant`; shares its portable `mail-evidence` input
layer, borrows (does not import) its `ClientProfile`/ledger shapes.

## Non-negotiable invariants

1. **Read-only on the mailbox.** Input uses `mail-evidence` IMAP EXAMINE — never SET flags,
   never move/delete/mark mail. Enforce in code, not just prompt.
2. **It informs; it never acts.** No replying to clients/subs, no scheduling, no commitments on
   Avigail's behalf. The single outbound channel is the digest itself, and **only ever to
   Avigail's own address** (`DIGEST_EMAIL_TO` allowlist; a non-allowlist recipient raises).
3. **Privacy.** Real correspondence stays in git-ignored `fixtures/`, `state/`, `out/`, `eval/`.
   No secrets in the repo — Keychain / git-ignored `.env`; gitleaks guards.
4. **Never fold into / out of the sibling.** Consume `mail-evidence` only through its protocols
   (`RelevanceJudge`, `ContactStore`); never add a daily-summary import into that package (a
   portability guard test in the sibling fails the build if domain coupling sneaks in).
5. **The model proposes; the human confirms.** The MODEL PASS writes only agent-proposed +
   observed state. Human-confirmed fields are written only via Avigail's feedback/override
   channel — the deterministic layer must never write them.

## Working agreement

- **Test-driven, always.** Write the failing test first, then the code. No exceptions.
- Read the `docs/` section a task names before coding — schema/algorithm are pinned there, not
  inferred from memory.
- One bounded component per task; stop at its acceptance criteria in `docs/06-build-plan.md`.
- **Recall is the gate, precision is informational.** Over-surface (even low-confidence threads);
  Avigail prunes/flags-off via feedback. Losing an important email is the worst failure.
- At each milestone: `docs/reviews/REVIEW-<date>.md` (commits since last review + scope), external
  review, fix cycle, then tag `review-<date>`.

## Repo map

| Area | Code | Spec to read first |
| --- | --- | --- |
| Domain state (clients/projects/tasks) | `digest/digest_core/state.py` | `docs/01-state-model.md` |
| Pipeline (bootstrap + daily) | `digest/digest_core/{bootstrap,daily,cli}.py` | `docs/02-pipeline.md` |
| Model seam | `digest/digest_core/reasoner.py`, `schema.py`, `apply.py` | `docs/05-model-seam.md` |
| TODO model + prioritization | `digest/digest_core/todos.py` | `docs/03-todo-model.md` |
| Delivery + feedback | `digest/digest_core/{delivery,feedback}.py` | `docs/04-delivery.md` |
| Shared input layer | `mail_evidence` (editable from sibling) | sibling `docs/mail-evidence-SPEC` |

## Current phase

See `docs/06-build-plan.md` → "Current phase". Update that pointer as phases close.
