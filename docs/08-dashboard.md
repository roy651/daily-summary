# 08 — Dashboard (Phase 2)

> **Status (2026-06-08):** v1 (2a+2b) BUILT + tested (`digest_web/`, 194 green) — read-only tabs + tombstone actions. Pending deploy to the mini-pc (it was unreachable at build time). Deploy kit in `deploy/`.

A local-network web dashboard for Avigail: view the same morning digest in a browser and **interact**
with it (close/add/edit todos, change a project's status, add/dismiss project notes, fix contact
roles, retract a wrong fact). Code: `digest_web/` (new package; imports `digest_core`, never imported
*into* it — same boundary as `mail-evidence`).

## Guiding principle

The dashboard is **Avigail's confirm/override surface**. The product invariant holds: *it informs, it
never acts externally* — the dashboard's only writes are her own confirmations to her own state, never
an email or client-facing action. It maps onto the existing three-way separation: the cron writes
*observed* + *agent-proposed*; the dashboard writes *human-confirmed*. It is a GUI over the
feedback/correction channel we already built, plus a few new write types.

## Stack

FastAPI + Jinja2 server-rendered HTML + **HTMX** (inline actions as partial-HTML swaps — no SPA, no
build step), served by Uvicorn on the mini-pc. Tailwind via CDN (or small hand CSS). Mobile-responsive.
Rationale: lowest-maintenance path for a single user; reuses `digest_core` directly; no JS build chain.

## Architecture — single shared model + tombstones

**One data model.** Both the cron and the dashboard write the same `state/*.json` directly — no sidecar
override store. Concurrency is not a concern (cron runs once each morning; the dashboard is used during
the day). The only safety: **atomic writes** (temp-file + rename) so a write is never half-applied.

**Deletions are tombstones, not hard deletes.** This is the answer to re-surfacing: the cron re-derives
from the same evidence, so a hard-deleted item just reappears next morning. Instead, when Avigail
closes a todo / dismisses a note / archives a project, we **flag** it (`done` / `dismissed` /
`status_confirmed=archived`) tagged **human-confirmed**. Two mechanisms keep it dead:

1. The merge already honors provenance (`state.SOURCE_RANK`: human > billing > model) — the model
   cannot resurrect a human-killed item.
2. The reasoner is told in its packet which items are closed/dismissed, so it won't re-propose them
   (and the deterministic layer drops it if it does).

This completes the pattern already used for suppressed threads, `closed_todos`, `status_confirmed`, and
knowledge-retract — not a new subsystem.

### Tombstone scope (important)

- **Item-level** (closed todo, dismissed note): id-specific and sticky. A new client email makes a
  *new* item (new id) that surfaces normally; the tombstone only suppresses *that* item.
- **Lifecycle-level** (project archive): provenance-based revival —
  - *model-archived* (decayed) + new evidence → **auto-revive**;
  - *Avigail-archived* + new evidence → **do not auto-revive; surface a prompt** ("📨 Archived project
    'X' got a new email — revive?") in the digest's "Also worth a look" + a one-click **Revive** button.
  - Respects her decision (no silent auto-undo) AND recall-is-the-gate (no silent burial). Reuses
    `apply.py`'s reversible-revival path.

## Schema additions (small, in `digest_core`)

- **Stable `id` on todos and observations** — so a flag targets the right item across regeneration.
- **Durable closed flag/ledger for todos** (human-confirmed) — survives re-derivation.
- **`Observation.dismissed`** flag (human-confirmed) — a dismissed note stays hidden, isn't re-added.
- **`Todo.source = human|model`** — her added/edited todos persist, never clobbered by carry-forward.

All written only by the dashboard (the human channel); the cron reads + respects them (the existing
no-confirmed-write guard still holds).

## Pages / tabs

1. **Today** (landing) — the morning digest as interactive HTML: each todo has close / edit / snooze;
   "Also worth a look" items get one-click confirm/dismiss/revive; project headers link through.
2. **Projects** — per project: status dropdown (→ `status_confirmed`), todos (add/edit/close/reorder),
   notes (add/dismiss), key contacts.
3. **Todos** — cross-project board (by project or urgency), add/close/edit.
4. **Contacts / People** — roles; fix a role or merge two addresses (writes a correction/alias).
5. **Knowledge** — tacit-knowledge notes; add one, or retract a wrong one (`forget:`).
6. **Clients** — agency flags, managing contacts.
7. *(2c)* **Leads** (accept→create project / dismiss→suppress) and **Archive** (revive an archived
   project in one click).

## Interactions

Her asks: close todo · add/edit todo · change status · add note · dismiss note. Plus: **snooze** a todo
N days · **revive** an archived project · **mute a sender / suppress a thread** (the configurable
mute-list deferred as J6/J7 lives here) · **confirm entity/role** questions · **accept/dismiss a lead**
· **undo last** (an action is a flag; undo = clear it) · **search** · **"Run now"** to trigger the
pipeline on demand (explicit, behind a spinner — costs a model run; this is also where an on-demand
wider-window "catch me up" could live).

## Deployment (mini-pc, home LAN)

Uvicorn as a systemd/launchd service alongside the cron; auto-restart. Avigail opens
`http://<minipc>:<port>` from her Mac/phone. **No auth** (LAN-only, trusted home network) for now. The
dashboard reads the cron's morning output; "refresh" re-reads current state (cheap); the model only
runs on the explicit "Run now".

## Testing

FastAPI `TestClient` per endpoint: assert the correct tombstone/field is written AND that
agent/observed fields are untouched (the invariant, as a test). Merge + "daily run respects tombstones"
(closed todo stays closed, dismissed note stays gone, human-archived project surfaces-not-auto-revives)
get unit/integration tests in `digest_core`. Test-first, as everywhere in the repo.

## Phasing

- **v1 = 2a + 2b together.** 2a: read-only dashboard (digest + tabs) deployed on the mini-pc. 2b: the
  tombstone schema additions + the core interactions (close/edit/add todo, status, add/dismiss note,
  revive) + "Run now". Daily run honors all tombstones.
- **2c (later):** contact role fixes/merges, knowledge retract UI, leads, mute-list, snooze, search,
  mobile polish.

Each phase ends with a milestone review (`docs/reviews/`), as everywhere in the repo.
