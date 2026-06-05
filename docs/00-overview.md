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

Design pillars: a swappable **MODEL PASS** (session / api / replay), a swappable **Delivery**
backend (file / email), and a strict separation of *agent-proposed* vs *human-confirmed* state.

Read next: `01-state-model.md`.
