# RUNBOOK

How to operate daily-summary. (Status: stub — fill in as the CLI lands.)

## One-time setup

```
uv sync                       # installs deps + editable mail-evidence
uv run pre-commit install
cp .env.example .env          # fill IMAP creds (or use Keychain in production)
```

## Bootstrap (cold start, once)

```
uv run python -m digest_core.cli bootstrap --holdout-days 7
```
Reads the sibling's mail export once, builds `state/clients.json` + `projects.json` + `contacts.json`,
holding out the last ~7 days for ground-truth collection. Re-run needs `--force`.

## Daily run (supervised, MVP)

```
REASONER=session DELIVERY=file uv run python -m digest_core.cli daily
```
Then provide the model pass in-session (reads `packet.json`, writes `model_output.json`). Output
lands in `out/`.

## Scheduling (external — not installed by this repo)

Add a cron / launchd entry that runs `python -m digest_core.cli daily`. Later this same command is
delegated to the Hermes host (copy the package dir + register a `job.json` whose prompt runs it).

## Ground-truth backtest (dev)

```
uv run python -m digest_core.cli daily --as-of 2026-06-01   # replay a held-out day
```
Repeat across the held-out week; collect Avigail's GT into `eval/gt/`. See `docs/07-acceptance.md`.
