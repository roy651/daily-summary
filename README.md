# daily-summary

A daily business digest for a freelance design studio: read the day's correspondence
(email now, Zoom transcripts later) and produce a short morning summary of what happened
and the likely to-dos. **Read-only** — it informs, it never acts.

Sibling product to [`invoicing-assistant`](../private/invoicing-assistant), with which it
shares its input layer (the portable `mail-evidence` conditioning engine).

## Status

Phase 1 (MVP) is built and runs end-to-end against real mail: condition mail → reasoning
packet → MODEL PASS → guarded apply → render (project status + ~24h updates + prioritized
todos) → deliver → persist, with a closed feedback loop (Avigail's corrections retract stale
facts and merge mis-identified contacts). See [`docs/STATUS.md`](docs/STATUS.md) for the
zoom-out and [`docs/06-build-plan.md`](docs/06-build-plan.md) for the current phase.

## Run it

```
uv sync
cp .env.example .env          # fill IMAP creds
uv run python -m digest_core.cli daily --dry-run
```

Full operating guide — backends, on-demand runs, how Avigail corrects things, scheduling —
is in [`docs/RUNBOOK.md`](docs/RUNBOOK.md). The design docs are [`docs/00-overview.md`](docs/00-overview.md)
→ `07`; [`.claude/handoff.md`](.claude/handoff.md) covers the shared `mail-evidence` foundation.
