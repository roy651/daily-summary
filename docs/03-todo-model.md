# 03 — TODO model + prioritization

Code: `digest/digest_core/todos.py`. (Status: stub.)

## Categories (extensible enum — revisit with Avigail)

- `self` — Avigail does it herself (design a brochure). `target` = None.
- `verify_subcontractor` — confirm a sub is progressing/done. `target` = the sub.
- `communicate_client` — ask/answer a client or SPRIG agent. `target` = the agent/client/end-client.

## Prioritization (deterministic — model proposes, Python ranks)

Composite urgency from three signals; kept out of the model so it is testable and stable run-to-run:
1. **Deadline pressure** — days to a `hard` deadline (from todo `due_hint`, else project `deadline`).
2. **Blocker leverage** — an action that *unblocks* a blocked project outranks a `self` action on
   an unblocked one. A "waiting on client" item is low priority *for Avigail* (ball not in her
   court) unless the chase has gone stale.
3. **Staleness** — `run_date - last_activity_date`. Silent + ball-in-her-court → escalate. Silent +
   waiting-on-client → escalate into a `communicate_client` chase.

Score → bands `urgent` / `soon` / `whenever`. Render grouped by band → category → client.
Deterministic tie-break (`project_id`) for golden-test stability.

**Carry-forward:** open todos persist across runs; the deterministic layer never deletes one the
model didn't address — it carries it and bumps staleness ("surface, don't drop").
