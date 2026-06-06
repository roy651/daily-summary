"""Headless entry point (docs/02-pipeline.md, RUNBOOK.md).

A clean, unattended-capable CLI — no interactive prompts, config via env/flags, deterministic exit
codes (0 ok, 1 usage/guard error, 2 model pass pending). Scheduling stays external (cron / launchd /
Hermes invoke this). Subcommands: bootstrap | daily | feedback | review | score | show.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Mapping
from datetime import date, timedelta
from pathlib import Path

from mail_evidence import ingest_email_export

from digest_core.bootstrap import run_bootstrap
from digest_core.contacts import DigestContactStore
from digest_core.daily import run_digest
from digest_core.delivery import select_delivery
from digest_core.evidence import condition_records, window_records
from digest_core.knowledge import KnowledgeStore
from digest_core.reasoner import SessionPending, select_reasoner
from digest_core.relevance import KeepAllHumanJudge
from digest_core.render import render_state_review_md
from digest_core.state import (
    ClientProfile,
    Project,
    load_clients,
    load_projects,
    write_clients,
    write_projects,
)

log = logging.getLogger("digest")


def _self_addresses(env: Mapping[str, str]) -> set[str]:
    """All of Avigail's own addresses — used to recognize our own outbound digest (and her reply) and to
    mark mail direction. Covers the legacy/single IMAP user, every multi-account IMAP user, the SMTP
    From (the digest is sent from there), and the digest recipient."""
    addrs = {
        env.get("IMAP_USER", ""),
        env.get("SMTP_USER", ""),
        env.get("DIGEST_EMAIL_TO", ""),
    }
    for name in env.get("IMAP_ACCOUNTS", "").split(","):
        if name.strip():
            addrs.add(env.get(f"IMAP_{name.strip().upper()}_USER", ""))
    return {a.strip().lower() for a in addrs if a.strip()}


def _today() -> str:
    return date.today().isoformat()


_MIN_WINDOW_DAYS = 2  # a digest always highlights at least the last 2 days...


def _digest_window_since(args, state_dir: Path, run_date: str) -> str:
    """The 'highlight as recent' window start. Prescribed windows win: --since DATE, or --window-days N
    (use for backlog / re-bootstrap). Otherwise AUTO: at least MIN days back, but extend as far as the
    oldest per-account watermark, so a late/skipped run still highlights everything that was pulled —
    the model never has to reason about the window itself."""
    if args.since:
        return args.since
    rd = date.fromisoformat(run_date)
    if args.window_days is not None:
        return (rd - timedelta(days=args.window_days)).isoformat()
    floor = (rd - timedelta(days=_MIN_WINDOW_DAYS)).isoformat()
    try:
        from mail_evidence import load_watermark
        from mail_evidence.config import load_imap_accounts

        marks = [load_watermark(state_dir, name=a.name) for a in load_imap_accounts()]
        dates = [m.date().isoformat() for m in marks if m]
    except Exception:  # offline / no accounts configured — just use the floor
        dates = []
    return min([floor, *dates]) if dates else floor


def _load_state(
    state_dir: Path,
) -> tuple[list[Project], list[ClientProfile], DigestContactStore]:
    projects = (
        load_projects(state_dir / "projects.json")
        if (state_dir / "projects.json").exists()
        else []
    )
    clients = (
        load_clients(state_dir / "clients.json")
        if (state_dir / "clients.json").exists()
        else []
    )
    contacts = DigestContactStore.load(state_dir / "contacts.json")
    knowledge = KnowledgeStore.load(state_dir / "knowledge.json")
    return projects, clients, contacts, knowledge


# ── subcommands ──────────────────────────────────────────────────────────────────


def _cmd_bootstrap(args, env: Mapping[str, str]) -> int:
    state_dir = Path(args.state_dir)
    if (state_dir / "projects.json").exists() and not args.force:
        log.error(
            "state/projects.json already exists — refusing to clobber. Use --force to re-bootstrap."
        )
        return 1

    export_root = args.export_root or env.get("SIBLING_EXPORT_ROOT")
    if not export_root:
        log.error("no export root: pass --export-root or set SIBLING_EXPORT_ROOT")
        return 1

    run_date = args.as_of or _today()
    records = ingest_email_export(export_root)
    reasoner = select_reasoner(
        env, work_dir=state_dir, run_date=run_date, replay_path=env.get("REPLAY_OUTPUT")
    )
    try:
        result = run_bootstrap(
            records=records,
            reasoner=reasoner,
            run_date=run_date,
            holdout_days=args.holdout_days,
            self_addresses=_self_addresses(env),
            knowledge=KnowledgeStore.load(state_dir / "knowledge.json"),
            since=args.since,
        )
    except SessionPending as pending:
        log.warning(str(pending))
        return 2

    log.info(
        "bootstrap: %d projects, %d clients, %d contacts",
        len(result.projects),
        len(result.clients),
        len(result.contacts.items()),
    )
    if args.dry_run:
        log.info("dry-run: not writing state")
        return 0
    write_projects(result.projects, state_dir / "projects.json")
    write_clients(result.clients, state_dir / "clients.json")
    result.contacts.save(state_dir / "contacts.json")
    result.knowledge.save(state_dir / "knowledge.json")
    return 0


def _cmd_daily(args, env: Mapping[str, str]) -> int:
    state_dir, out_dir = Path(args.state_dir), Path(args.out_dir)
    projects, clients, contacts, knowledge = _load_state(state_dir)
    run_date = args.as_of or _today()
    since = _digest_window_since(args, state_dir, run_date)
    span = (date.fromisoformat(run_date) - date.fromisoformat(since)).days
    if span > 31:
        log.warning(
            "digest window is %d days (since %s) — over a month. Proceeding; pass --since/--window-days "
            "to constrain, or this is expected for a backlog/re-bootstrap run.",
            span,
            since,
        )

    # Replay of a past day must be offline + non-mutating (F7): no live pull, no watermark.
    if args.as_of and not args.from_export:
        log.error(
            "--as-of replays a past day and must read an offline source; pass --from-export PATH"
        )
        return 1

    if args.from_export:
        records = window_records(
            ingest_email_export(args.from_export),
            since=args.ingest_since,
            until=args.ingest_until,
        )
        threads = condition_records(
            records, judge=KeepAllHumanJudge(), contact_store=contacts
        )
        watermark_commit = None
    else:
        threads, watermark_commit = _live_pull(env, contacts, state_dir)

    reasoner = select_reasoner(
        env, work_dir=state_dir, run_date=run_date, replay_path=env.get("REPLAY_OUTPUT")
    )
    delivery = select_delivery(env, out_dir=out_dir, dry_run=args.dry_run)
    try:
        result = run_digest(
            projects=projects,
            clients=clients,
            contacts=contacts,
            threads=threads,
            reasoner=reasoner,
            delivery=delivery,
            run_date=run_date,
            since=since,
            self_addresses=_self_addresses(env),
            state_dir=state_dir,
            out_dir=out_dir,
            knowledge=knowledge,
            persist=not args.dry_run,
        )
    except SessionPending as pending:
        log.warning(str(pending))
        return 2

    log.info(
        "daily: delivered=%s (%s); %d filtered; %d todos closed from feedback; %d suspected to confirm",
        result.delivery.sent,
        result.delivery.detail,
        len(result.filtered),
        result.closed_from_feedback,
        len(result.suspected),
    )
    # Advance the watermark only after a successful, persisted, present-day delivery (never on replay).
    if (
        watermark_commit is not None
        and result.delivery.sent
        and not args.dry_run
        and not args.as_of
    ):
        watermark_commit()
    return 0


def _cmd_feedback(args, env: Mapping[str, str]) -> int:
    run_date = args.as_of or _today()
    delivery = select_delivery(env, out_dir=Path(args.out_dir))
    feedback = delivery.collect_feedback(run_date=run_date)
    if feedback is None:
        log.info("no feedback found")
        return 0
    out = Path(args.state_dir) / "feedback" / f"feedback_{run_date}.json"
    feedback.save(out)
    log.info(
        "feedback captured -> %s (%d done, %d open, %d suppressed)",
        out,
        len(feedback.eod_actuals),
        len(feedback.revised_todos),
        len(feedback.suppressed_threads),
    )
    return 0


def _cmd_review(args, env: Mapping[str, str]) -> int:
    projects, clients, contacts, _ = _load_state(Path(args.state_dir))
    out = Path(args.out_dir) / "state-review.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        render_state_review_md(clients, projects, contacts), encoding="utf-8"
    )
    log.info("state review -> %s", out)
    return 0


def _cmd_score(args, env: Mapping[str, str]) -> int:
    from digest_core.evaluation import GroundTruth, score_digest

    digest_md = Path(args.digest).read_text(encoding="utf-8")
    result = score_digest(digest_md, GroundTruth.load(args.gt))
    print(f"recall {result.matched}/{result.total} = {result.recall:.2f}")
    for phrase in result.missed:
        print(f"  MISSED: {phrase}")
    return 0


def _cmd_show(args, env: Mapping[str, str]) -> int:
    projects, clients, contacts, _ = _load_state(Path(args.state_dir))
    print(
        f"clients: {len(clients)}  projects: {len(projects)}  contacts: {len(contacts.items())}"
    )
    for p in sorted(projects, key=lambda p: (p.client_id, p.project_id)):
        print(f"  [{p.status}] {p.client_id}/{p.project_id}: {p.title}")
    return 0


def _live_pull(env: Mapping[str, str], contacts: DigestContactStore, state_dir: Path):
    """Read-only IMAP pull via mail-evidence across ALL configured accounts (e.g. ULA + Gmail), each
    with its OWN watermark. Returns (merged_threads, commit_watermarks_callable). Threads dedup by
    Message-ID downstream, so overlapping accounts are safe. Watermarks advance only after delivery."""
    from mail_evidence import (
        FetchConfig,
        ImapClient,
        commit_watermark,
        load_watermark,
        run,
    )
    from mail_evidence.config import load_imap_accounts

    accounts = load_imap_accounts()
    if not accounts:
        raise RuntimeError(
            "no IMAP accounts configured: set IMAP_ACCOUNTS=ula,gmail + IMAP_<NAME>_HOST/PORT/USER/"
            "APP_PASSWORD (or legacy IMAP_HOST/IMAP_USER/IMAP_APP_PASSWORD for a single account)."
        )

    threads: list = []
    highwater: list[tuple[str, object]] = []
    for acct in accounts:
        watermark = load_watermark(state_dir, name=acct.name)
        log.info(
            "pull account=%s host=%s inbox=%r sent=%r since=%s",
            acct.name,
            acct.host,
            acct.inbox_folder,
            acct.sent_folder,
            watermark.isoformat() if watermark else "cold start",
        )
        client = ImapClient(
            acct.host, acct.port, acct.user, acct.password, mailbox=acct.inbox_folder
        )
        # Per-account folders — Gmail's sent folder is '[Gmail]/Sent Mail', not 'Sent' (the override
        # comes from IMAP_<NAME>_SENT). Without this the default FetchConfig asks every account for 'Sent'.
        config = FetchConfig(
            inbox_folder=acct.inbox_folder, sent_folder=acct.sent_folder
        )
        latest = watermark
        for batch in run(config, KeepAllHumanJudge(), contacts, client, watermark):
            threads.extend(batch)
            for t in batch:
                for r in t.records:
                    latest = r.date if latest is None or r.date > latest else latest
        if latest is not None and latest != watermark:
            highwater.append((acct.name, latest))

    def commit():
        for name, latest in highwater:
            commit_watermark(latest, state_dir, name=name)

    return threads, commit


# ── arg parsing ────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="digest_core.cli",
        description="Avigail's daily business digest (read-only).",
    )
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser(
        "bootstrap", help="one-shot cold-start map build from a mail export"
    )
    b.add_argument("--export-root")
    b.add_argument(
        "--since",
        help="lower-bound ingest date (YYYY-MM-DD); pair with --as-of to bootstrap one month",
    )
    b.add_argument("--holdout-days", type=int, default=7)
    b.add_argument("--force", action="store_true")
    b.add_argument("--dry-run", action="store_true")
    b.add_argument("--as-of")
    b.add_argument("--state-dir", default="state")
    b.set_defaults(func=_cmd_bootstrap)

    d = sub.add_parser("daily", help="produce + deliver today's digest")
    d.add_argument("--state-dir", default="state")
    d.add_argument("--out-dir", default="out")
    d.add_argument("--as-of")
    d.add_argument(
        "--since",
        help="prescribe the digest window start (YYYY-MM-DD) — e.g. a backlog load",
    )
    d.add_argument(
        "--window-days",
        type=int,
        default=None,
        help="prescribe a fixed N-day window; default auto-extends from 2 days to the watermark",
    )
    d.add_argument(
        "--from-export", help="ingest a local mail export instead of a live IMAP pull"
    )
    d.add_argument(
        "--ingest-since", help="lower-bound date filter for --from-export (YYYY-MM-DD)"
    )
    d.add_argument(
        "--ingest-until",
        help="upper-bound (exclusive) date filter for --from-export (YYYY-MM-DD)",
    )
    d.add_argument("--dry-run", action="store_true")
    d.set_defaults(func=_cmd_daily)

    f = sub.add_parser(
        "feedback", help="collect + persist Avigail's feedback (no model)"
    )
    f.add_argument("--state-dir", default="state")
    f.add_argument("--out-dir", default="out")
    f.add_argument("--as-of")
    f.set_defaults(func=_cmd_feedback)

    r = sub.add_parser("review", help="render the client/project map for review")
    r.add_argument("--state-dir", default="state")
    r.add_argument("--out-dir", default="out")
    r.set_defaults(func=_cmd_review)

    sc = sub.add_parser(
        "score", help="score a produced digest against a ground-truth file"
    )
    sc.add_argument("--digest", required=True)
    sc.add_argument("--gt", required=True)
    sc.set_defaults(func=_cmd_score)

    s = sub.add_parser("show", help="print current state (read-only)")
    s.add_argument("--state-dir", default="state")
    s.set_defaults(func=_cmd_show)
    return p


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stderr
    )
    # Load ./.env automatically (parsed safely by python-dotenv — never `source` it). Existing shell
    # env wins (override=False), so `DELIVERY=file uv run ... daily` still overrides the file.
    from dotenv import load_dotenv

    load_dotenv()
    env = env if env is not None else os.environ
    args = build_parser().parse_args(argv)
    return args.func(args, env)


if __name__ == "__main__":
    raise SystemExit(main())
