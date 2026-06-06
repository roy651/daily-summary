# 00 — Overview

daily-summary reads Avigail's correspondence (email now; Zoom transcripts in phase 1.5) and
produces a read-only morning digest with three sections: **project status**, **important updates
(last ~24h)**, and a **prioritized TODO list**. It reasons over a conditioned reasoning packet;
it never acts on her behalf.

Pipeline at a glance (see `02-pipeline.md`):

```
bootstrap (one-shot)   sibling mail export ─ingest─> initial clients/projects/contacts map
daily (recurring)      mailbox ─pull─> condition ─> reasoning packet ─MODEL PASS─>
                       update state + digest + todos ─> deliver (file | email) ─> persist
```

Design pillars: a swappable **MODEL PASS** (`code` headless Claude Code / `api` / `session` /
`replay` — see `05`), a swappable **Delivery** backend (file / email), a strict separation of
*observed* / *agent-proposed* / *human-confirmed* state, and a **closed feedback loop** — Avigail's
corrections retract stale facts and merge mis-identified contacts so the map self-heals (`04`/`05`).

Read next: `01-state-model.md`.
