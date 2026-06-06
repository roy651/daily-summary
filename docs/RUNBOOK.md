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
Avigail, persists state, and advances the watermarks. **One knob — the `--dry-run` flag:**
- `daily --dry-run` → pull + reason + write the `out/` artifacts to read, but **don't** send, persist, or move the watermark.
- `daily` → real run: send to Avigail, persist state, advance per-account watermarks.

The digest **window** is automatic: it highlights everything since the last run (extends back to the
oldest watermark, minimum 2 days) and just warns if that span exceeds a month — so you never reason
about the window. Override only for backlog/re-bootstrap: `--since YYYY-MM-DD` or `--window-days N`.

The CLI loads `./.env` itself (via python-dotenv) — **do not `source` the `.env`** (it isn't shell
script; sourcing it can execute stray words). Just run from the repo directory:

```bash
cd /path/to/daily-summary

# 1) Preview — pull both mailboxes, reason via your subscription, write out/digest_<date>.md to read.
#    Nothing sent, nothing persisted, watermark unchanged:
uv run python -m digest_core.cli daily --dry-run

# 2) Real run — same, then email Avigail, persist state, advance both watermarks:
uv run python -m digest_core.cli daily

# 3) feedback is automatic on the NEXT run: the email backend finds her reply to the digest in the
#    pulled mail and applies it (done:/archive:/revive:/suppress: + free-text notes -> knowledge).
#    File backend instead reads your edits to out/todos.md; `feedback` captures it without a model pass:
uv run python -m digest_core.cli feedback
```

**How Avigail corrects things** — reply to the digest email (or edit `out/todos.md` on the file
backend). Directives (`#` prefix in the file, bare in an email reply):
- `done: …` close a todo · `archive: <project-id>` / `revive: <id>` · `suppress: <thread-id>` hide a thread
- `forget: <text>` **delete a wrong fact** from knowledge (paste a bit of its text)
- `alias: a@x.com, b@y.com = subcontractor` **declare addresses are one person** + set their role
- any other prose becomes a **knowledge note**, tagged authoritative so the reasoner trusts it over its
  own guess.

Corrections are applied by both Avigail *and the reasoner itself*: when a confirmed note or clear
evidence contradicts an existing fact/role, the model emits a `corrections` entry to **retract** the
stale knowledge and **merge** the mis-identified contacts — so false facts don't linger (e.g. the
Rock-Design = Idan case). Her reply is recognised by the `digest:` subject tag (from her address) and is
never fed back in as project evidence.

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
uv run python -m digest_core.cli daily >> state/cron.log 2>&1
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
