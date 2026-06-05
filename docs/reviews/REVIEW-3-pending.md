# Review 3 — pending findings (collected during the real-data backfill)

Running collection for the next external review. Surfaced while backfilling Feb→May on real mail.
These are mostly about **first-pass reasoning precision** and the **human-interaction surface** — not
the deterministic core (which the prior reviews accepted). They compound with reviewer K2 (knowledge
provenance) and N3 (contact roles).

## C1 — Entity & role resolution is the weakest reasoning step (client vs sub vs agent vs internal)

Two real mis-classifications in one backfill: **Katie** (a SPRIG manager) and **Lee Kurzweil** (an
illustrator subcontractor) were each modeled as their *own client*. Recall never failed (their
threads were surfaced) and the human caught both — but first-pass precision on "who is this new
entity?" is poor, and it's the highest-impact call (a wrong role mis-attributes a whole project).

*Why it happens:* the packet is project/thread-centric. Creating a new `client_id` isn't challenged;
there's no forcing function to classify a new person as **client** (work done FOR them), **sub**
(their output FEEDS Avigail's deliverables, e.g. an illustrator), **agent** (coordinates on the
agency side), or **internal** (ula). And no reasoning-by-analogy to known roles (we already know
Nurit/Idan/Maya/Idan Zal are subs; a new illustrator doing feed-in work is almost certainly a sub).

*Proposed:* (a) an explicit "entity & role resolution" instruction in the packet/prompt; (b) check
new entities against known-role analogues; (c) see C3 (surface for confirmation). Matters MORE for
the headless `ApiReasoner` — no human pre-screens before the digest there.

## C2 — Billing direction is the cleanest role signal, and it's currently ignored/dropped

**Owner's framing (key):** it's broader than morning.co notifications — it's **any invoice in the
mail, inbound or outbound**:
- **Outbound invoice** (issued by Avigail / ULA Studio) → the **recipient is a CLIENT** (a payer).
- **Inbound invoice** (billed TO Avigail / ULA) → the **sender is a SUBCONTRACTOR / vendor**.

This single rule would have correctly typed Lee (she invoices Avigail → sub) and Katie/SPRIG
(Avigail invoices them → client/agency), and it generalizes: e.g. `idan@rockdesign.co.il חשבונית`
(inbound) in the May batch ⇒ Rock Design is a dev vendor/sub. *Today the system never uses this:*
morning.co/ESP invoice notices risk being dropped by N2/bulk, and we don't parse invoice
direction at all. *Proposed:* detect invoice/billing emails, infer direction (from/to ULA), and
persist it as durable **relational knowledge** ("X invoices Avigail ⇒ sub"; "Avigail invoices Y ⇒
client"); never let denoise discard them. This is probably the highest-leverage precision fix.

## C3 — New entities aren't surfaced for human confirmation

New clients/contacts are created silently inside a big update, so a mis-role is only caught if the
human happens to read the JSON. *Proposed:* a digest section **"New entities this run — confirm
role"** (new clients + newly-promoted contacts + inferred role + the one-line basis), so role errors
are caught systematically every run, the same way the owner caught Katie/Lee — but without luck.

## C4 — Human-interaction surface (how Avigail views + corrects the map)

Owner asked how Avigail sees the project map and adds notes/corrections. Today:
- **View:** `digest review` → `out/state-review.md` (human-readable). Raw store is `state/*.json`.
- **Edit:** hand-edit `state/*.json` (round-trip safe) — works but technical; OR the feedback channel
  (edit `out/todos.md` / reply to the digest email) which is **parsed + captured** to `state/feedback/`
  but **not yet consumed** into knowledge/state (phase 2).

*Gaps to build:* (a) an **on-demand polished report** (the owner suggested md/PDF, to file or email)
— `digest review` already emits md; add PDF + email-on-demand; (b) **feedback-driven editing** — let
Avigail drop notes in the feedback mail / review file and have the system route them into
`knowledge.json` / client `observations` / **role overrides** (so she never edits JSON). This is the
consume half of the learning loop (K2-adjacent): tag provenance so human-confirmed notes outrank
agent-inferred ones.

## D1 — Past/overdue deadlines invert to MAXIMUM urgency (prioritization bug)

`todos._score` does `score += max(0, 30 - days_to_due) * weight`. When `days_to_due` is negative (the
deadline has passed), `30 - days_to_due` grows, so an **overdue** hard deadline scores *higher* and
lands in the "Urgent" band. Visible in the May-18 digest: the Urgent band is entirely Feb/Apr RMX
CRT-booth todos whose (April) deadline is long past. *Fix:* clamp/branch on `days_to_due < 0` — either
drop deadline pressure for past dates, or route overdue items to a distinct "Overdue — still open?"
treatment (likely they're done and just weren't closed → ties to D2). Cheap, high-visibility.

## D2 — Carry-forward TODO bloat: todos accumulate for months, never close

`merge_todos` carries forward any prior todo the model didn't restate ("surface, don't drop"), but
nothing ever *closes* one: the model isn't asked to, and the deterministic layer never ages/drops.
After a Feb→May backfill the digest's "Whenever" band holds ~60 todos, many clearly completed (e.g.
"Send Charlene the TurnCare invoice for February" in a May digest). Recall-first was right early, but
at horizon it makes the TODO list unusable. *Options:* (a) have the model emit explicit `done`/closed
todo ids each run; (b) age-out todos on projects with newer activity that didn't restate them; (c) for
a *touched* project, treat the model's todo set as authoritative (replace) rather than union; (d) cap
the rendered list per band + per project. Probably (a)+(d). This is the most user-visible quality gap
in the real digest and pairs with reviewer K1 (uncapped growth).

## Cross-refs
- Reviewer **K2** (knowledge provenance / human-confirmed tier) — C2/C4 need it: relational + billing
  facts and human corrections should be a confirmed tier that outranks agent guesses.
- Reviewer **N3** (contact-role granularity) — C1/C2 are the substantive version of it.
