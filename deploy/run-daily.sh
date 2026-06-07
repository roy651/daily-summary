#!/usr/bin/env bash
# Daily digest run, invoked by cron/systemd at 07:00 Asia/Jerusalem (Sun–Fri). Loads ./.env itself
# (do NOT `source` it). Single-instance lock so an overlapping/slow run can't double-send.
set -euo pipefail
REPO="${DAILY_SUMMARY_REPO:-$HOME/daily-summary}"
cd "$REPO"
mkdir -p state
exec 9>"state/.daily.lock"
flock -n 9 || { echo "$(date -Is) run already in progress — skipping"; exit 0; }
echo "=== $(date -Is) daily run starting ===" >> state/cron.log
uv run python -m digest_core.cli daily >> state/cron.log 2>&1
echo "=== $(date -Is) daily run done (exit $?) ===" >> state/cron.log
