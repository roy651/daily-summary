# Deploy — mini-pc (home LAN)

Runs two things on the always-on mini-pc: the **morning digest cron** (emails Avigail) and the
**dashboard** (she views/manages in a browser). Prereqs on the box: `uv`, and either `claude` logged in
(`REASONER=code`) or an API key (`REASONER=api`); plus a populated `.env` (IMAP/SMTP creds).

## 1. Copy the repo
```bash
# from this Mac (mini-pc reachable):
rsync -av --exclude .git --exclude fixtures --exclude state --exclude out \
  ~/Development/daily-summary/  roy650@<mini-pc>:~/daily-summary/
scp ~/Development/daily-summary/.env roy650@<mini-pc>:~/daily-summary/.env   # creds (git-ignored)
```

## 2. Install + seed (on the mini-pc)
```bash
cd ~/daily-summary
uv sync
chmod +x deploy/run-daily.sh
# Seed each account's watermark so the first run doesn't cold-start a huge window (set to "now"):
#   uv run python -m mail_evidence.runner watermark ...   (or carry over the Mac's state/ watermarks)
```

## 3. Schedule the morning cron (07:00 Israel, Sun–Fri)
```bash
crontab -e         # paste deploy/crontab.snippet (fix the path)
crontab -l         # verify
```

## 4. Dashboard service
```bash
sudo cp deploy/daily-summary-web.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now daily-summary-web
# Avigail → http://<mini-pc-ip>:8080
```
Then set `DASHBOARD_URL=http://<mini-pc-ip>:8080` in `.env` so the digest email links to it.

## Notes
- **State lives on the mini-pc** once cron runs there — don't also run the Mac cron, or the two diverge.
  Carry the Mac's `state/` over once (step 1 excludes it; copy manually if you want continuity).
- Read-only mailbox + outbound only to `DIGEST_EMAIL_TO` invariants are unchanged.
- `state/cron.log` has each run's output; the dashboard's `journalctl -u daily-summary-web` for the web.
