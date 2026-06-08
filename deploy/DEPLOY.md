# Deploy — mini-pc (home LAN)

Runs two things on the always-on mini-pc, both as **systemd `--user` services** (no sudo; `linger`
keeps them alive with no login):

- the **morning digest** — a timer fires `run-daily.sh` at 07:00 Israel and emails Avigail;
- the **dashboard** — Uvicorn she opens in a browser to view/manage the digest.

Prereqs on the box: `uv` and either `claude` logged in (`REASONER=code`) or an API key
(`REASONER=api`); a populated `.env` (IMAP/SMTP creds); and `loginctl enable-linger "$USER"`.

> **Why systemd, not cron:** Debian/Ubuntu's cron **silently ignores `CRON_TZ`**, so a
> `CRON_TZ=Asia/Jerusalem` + `0 7 …` crontab fires at 07:00 in the box's *own* timezone (UTC here =
> 10:00 Israel), never 07:00 Israel. systemd's `OnCalendar` honors the timezone and DST — so the
> schedule lives in `daily-summary.timer`, not a crontab.

## 1. Copy the repo (+ the sibling it depends on)

`mail-evidence` is an editable path dependency at `../invoicing-assistant/skills/mail-evidence`
(relative to the repo), so it must sit alongside the repo on the box.

```bash
# from this Mac (mini-pc reachable):
rsync -az --exclude .git --exclude .venv --exclude /fixtures --exclude /out --exclude /eval \
  --exclude __pycache__ --exclude '.*_cache' \
  ~/Development/private/daily-summary/  roy650@<mini-pc>:~/daily-summary/
rsync -az ~/Development/private/invoicing-assistant/skills/mail-evidence/ \
  roy650@<mini-pc>:~/invoicing-assistant/skills/mail-evidence/
rsync -az ~/Development/private/daily-summary/state/ roy650@<mini-pc>:~/daily-summary/state/  # continuity
scp ~/Development/private/daily-summary/.env roy650@<mini-pc>:~/daily-summary/.env            # git-ignored creds
```

Note: `rsync`'s `--exclude fixtures` must be anchored (`/fixtures`) — an unanchored `fixtures` also
drops the in-repo `digest/tests/fixtures/`, which the test suite needs.

## 2. Install + configure (on the mini-pc)

```bash
cd ~/daily-summary
uv sync --extra web
chmod +x deploy/run-daily.sh
loginctl enable-linger "$USER"     # user services survive logout/reboot
```

In `.env`, set: `REASONER=code`, `CLAUDE_BIN=$HOME/.local/bin/claude` (absolute — cron/systemd PATH is
minimal), `CLAUDE_MODEL=opus` (reliable todo extraction; Sonnet under-generates them),
`DELIVERY=email`, `DIGEST_EMAIL_TO=<avigail>`, and `DASHBOARD_URL=http://<mini-pc-ip>:8080` so the
email links to the dashboard. Carry the Mac's `state/` watermarks over (step 1) so the first run
doesn't cold-start a huge window.

## 3. Schedule the morning digest (07:00 Israel, Sun–Fri)

```bash
mkdir -p ~/.config/systemd/user
cp deploy/daily-summary.service deploy/daily-summary.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now daily-summary.timer
systemctl --user list-timers daily-summary.timer    # verify NEXT = 07:00 Israel
```

`state/cron.log` has each run's output. Trigger a real run by hand with
`systemctl --user start daily-summary.service` — **this sends a live email**; for a no-send check use
`uv run python -m digest_core.cli daily --dry-run`.

## 4. Dashboard service

```bash
cp deploy/daily-summary-web.service ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now daily-summary-web
sudo ufw allow from 192.168.1.0/24 to any port 8080 proto tcp   # open the LAN port (ufw is on)
# Avigail → http://<mini-pc-ip>:8080
```

`journalctl --user -u daily-summary-web` for the web logs. The dashboard's **Re-run digest** button
runs `daily --no-send` (regenerate + persist, no email, no watermark change) on demand.

## Notes

- **State lives on the mini-pc** once the timer runs there — don't also schedule the Mac, or the two
  diverge. `deploy/mac-fallback.plist` is a launchd fallback for the Mac *only if the mini-pc is down*
  (launchd runs in the Mac's local timezone; set the Mac to Israel time for it to mean 07:00 there).
- Read-only mailbox + outbound only to `DIGEST_EMAIL_TO` invariants are unchanged.
