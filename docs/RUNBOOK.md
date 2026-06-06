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

## Reasoning backends (`REASONER`)

The model pass is one swappable seam — pick a backend with the `REASONER` env var; everything else
is identical. All produce the same `ModelOutput`.

| `REASONER` | Who reasons | Auth / cost | Unattended |
| --- | --- | --- | --- |
| `code` (default) | headless Claude Code (`claude -p`) | your Claude **subscription**, no API key | ✅ |
| `api` | Anthropic SDK **or** any OpenAI-compatible endpoint (OpenRouter, Together, local) | per-token API key | ✅ |
| `session` | a supervised Claude session (you) | — | ❌ (pauses for `model_output.json`) |
| `replay` | a fixture file | — | tests |

`code` needs `claude` on `PATH` and logged in (`claude` once, interactively). `api` needs
`uv sync --extra api` and `LLM_PROVIDER` / `LLM_MODEL` / `LLM_API_KEY` (+ `LLM_BASE_URL` for
OpenAI-compatible). See `.env.example`.

## On-demand run (headless — produce today's digest)

Reads **both** mailboxes (`IMAP_ACCOUNTS=ula,gmail`) since each account's watermark, reasons, emails
Avigail, persists state, and advances the watermarks. Two independent safety knobs:
- **`DRY_RUN`** (env): `true` = reason + render but **do not actually send** (logs "would send"). Flip
  to `false` to send for real.
- **`--dry-run`** (CLI flag): additionally skip **persisting state + advancing the watermark** (pure preview).

The CLI loads `./.env` itself (via python-dotenv) — **do not `source` the `.env`** (it isn't shell
script; sourcing it can execute stray words). Just run from the repo directory:

```bash
cd /path/to/daily-summary

# 1) Preview — pull + reason + render, nothing sent, nothing persisted:
uv run python -m digest_core.cli daily --dry-run

# 2) Real run — pull both mailboxes, reason via your subscription, email Avigail,
#    persist state, advance per-account watermarks (set DRY_RUN=false in .env to actually send):
DRY_RUN=false uv run python -m digest_core.cli daily

# 3) Next morning — capture Avigail's reply (check-offs / # archive: / # suppress:) as feedback:
uv run python -m digest_core.cli feedback
```

First-ever live run: seed the watermark so it doesn't cold-start the whole window
(`FetchConfig` already bounds a cold start to 35 days / 500 msgs):
```bash
uv run python -c "from datetime import datetime,timezone; from pathlib import Path; \
from mail_evidence import commit_watermark; \
[commit_watermark(datetime(2026,6,3,23,59,59,tzinfo=timezone.utc), Path('state'), name=n) for n in ('ula','gmail')]"
```

## Scheduling (external — not installed by this repo)

The same `daily` command is what a scheduler runs every morning; the per-account watermark makes it
gap-safe and idempotent (threads dedup by Message-ID).

launchd (macOS) — run a small wrapper at 07:00 daily:
```bash
# run-digest.sh   (the CLI loads ./.env itself — no `source` needed)
cd /path/to/daily-summary || exit 1
DRY_RUN=false uv run python -m digest_core.cli daily >> state/cron.log 2>&1
```
```
launchctl ... StartCalendarInterval { Hour=7, Minute=0 }  → run-digest.sh
```
cron equivalent: `0 7 * * *  /path/to/run-digest.sh`. Later this same command is delegated to the
Hermes host (copy the package dir + register a `job.json` whose prompt runs it).

## Ground-truth backtest (dev)

```
uv run python -m digest_core.cli daily --as-of 2026-06-01   # replay a held-out day
```
Repeat across the held-out week; collect Avigail's GT into `eval/gt/`. See `docs/07-acceptance.md`.
