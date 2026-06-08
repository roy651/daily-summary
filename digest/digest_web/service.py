"""Read helpers for the dashboard — load the shared state + the latest rendered digest. Pure reads;
writes (tombstones) live in actions.py. State dir / out dir come from env so the same app runs against
the mini-pc's live state."""

from __future__ import annotations

import datetime
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import markdown

from digest_core.contacts import DigestContactStore
from digest_core.knowledge import KnowledgeStore
from digest_core.state import (
    ClientProfile,
    Project,
    load_clients,
    load_projects,
)
from digest_core.todos import RankedTodo, prioritize

_ISRAEL = ZoneInfo("Asia/Jerusalem")


def state_dir() -> Path:
    return Path(os.environ.get("STATE_DIR", "state"))


def out_dir() -> Path:
    return Path(os.environ.get("OUT_DIR", "out"))


def today() -> str:
    return datetime.date.today().isoformat()


def projects() -> list[Project]:
    f = state_dir() / "projects.json"
    return load_projects(f) if f.exists() else []


def clients() -> list[ClientProfile]:
    f = state_dir() / "clients.json"
    return load_clients(f) if f.exists() else []


def contacts() -> DigestContactStore:
    return DigestContactStore.load(state_dir() / "contacts.json")


def knowledge() -> KnowledgeStore:
    return KnowledgeStore.load(state_dir() / "knowledge.json")


def active_projects() -> list[Project]:
    """Projects shown in the dashboard: not done/archived, newest activity first."""
    act = [p for p in projects() if p.status not in ("done", "archived")]
    return sorted(act, key=lambda p: p.last_activity_date or "", reverse=True)


def archived_projects() -> list[Project]:
    return [p for p in projects() if p.status == "archived"]


def project(project_id: str) -> Project | None:
    return next((p for p in projects() if p.project_id == project_id), None)


def ranked_todos(run_date: str | None = None) -> list[RankedTodo]:
    return prioritize(active_projects(), run_date=run_date or today())


def last_run_at() -> str | None:
    """When the most recent digest was generated, as Israel-local 'Mon 08 Jun, 07:00' — the mtime of
    the newest out/digest_*.md (what the cron/run writes at the end of a run). None if none yet."""
    files = sorted(out_dir().glob("digest_*.md"))
    if not files:
        return None
    ts = datetime.datetime.fromtimestamp(files[-1].stat().st_mtime, tz=_ISRAEL)
    return ts.strftime("%a %d %b, %H:%M")


def latest_digest() -> tuple[str | None, str]:
    """(run_date, html_fragment) of the most recent out/digest_*.md, rendered for embedding."""
    files = sorted(out_dir().glob("digest_*.md"))
    if not files:
        return None, "<p><em>No digest generated yet.</em></p>"
    f = files[-1]
    run_date = f.stem.replace("digest_", "")
    html = markdown.markdown(
        f.read_text(encoding="utf-8"), extensions=["extra", "sane_lists"]
    )
    return run_date, html
