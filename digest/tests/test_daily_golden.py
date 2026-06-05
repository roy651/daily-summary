"""Golden end-to-end (docs/07-acceptance.md) — the Phase-1 acceptance gate.

Drives the real CLI on .eml fixtures with REASONER=replay + DELIVERY=file: offline emails -> condition
-> packet -> ReplayReasoner -> apply -> render -> deliver. Asserts the rendered digest byte-for-byte
against expected_digest.md and the prioritized todos against expected_todos.json. Also pins the two
load-bearing behaviors: a brand-new lead is surfaced, and the human-confirmed column stays unwritten.
"""

import json
import shutil
from pathlib import Path

from digest_core import cli
from digest_core.state import load_projects
from digest_core.todos import prioritize

FIX = Path(__file__).parent / "fixtures"


def _run(tmp_path):
    state_dir = tmp_path / "state"
    out_dir = tmp_path / "out"
    shutil.copytree(FIX / "state", state_dir)
    env = {
        "REASONER": "replay",
        "REPLAY_OUTPUT": str(FIX / "model_output_daily.json"),
        "DELIVERY": "file",
        "IMAP_USER": "avigail@ula.example",
    }
    code = cli.main(
        [
            "daily",
            "--from-export",
            str(FIX / "emails"),
            "--state-dir",
            str(state_dir),
            "--out-dir",
            str(out_dir),
            "--as-of",
            "2026-06-05",
        ],
        env=env,
    )
    assert code == 0
    return state_dir, out_dir


def test_digest_matches_golden(tmp_path):
    _, out_dir = _run(tmp_path)
    produced = (out_dir / "digest_2026-06-05.md").read_text()
    expected = (FIX / "expected_digest.md").read_text()
    assert produced == expected


def test_prioritized_todos_match_golden(tmp_path):
    state_dir, _ = _run(tmp_path)
    projects = load_projects(state_dir / "projects.json")
    ranked = prioritize(projects, run_date="2026-06-05")
    produced = [
        {
            "band": r.band,
            "category": r.todo.category,
            "project_id": r.project_id,
            "text": r.todo.text,
        }
        for r in ranked
    ]
    expected = json.loads((FIX / "expected_todos.json").read_text())
    assert produced == expected


def test_new_lead_is_surfaced(tmp_path):
    # A brand-new client (Maya, unknown contact) must be captured as a project — the core value.
    state_dir, _ = _run(tmp_path)
    projects = load_projects(state_dir / "projects.json")
    assert any(
        p.client_id == "studio-lev" and p.title == "Tri-fold brochure" for p in projects
    )


def test_existing_project_blocked_and_confirmed_untouched(tmp_path):
    state_dir, _ = _run(tmp_path)
    homepage = next(
        p
        for p in load_projects(state_dir / "projects.json")
        if p.project_id == "p-sprig-homepage"
    )
    assert homepage.status_agent == "blocked"
    assert homepage.last_activity_date == "2026-06-05"  # advanced from evidence
    assert (
        homepage.status_confirmed is None
    )  # guard: human column never written by apply


def test_dry_run_does_not_persist(tmp_path):
    state_dir = tmp_path / "state"
    out_dir = tmp_path / "out"
    shutil.copytree(FIX / "state", state_dir)
    env = {
        "REASONER": "replay",
        "REPLAY_OUTPUT": str(FIX / "model_output_daily.json"),
        "DELIVERY": "file",
        "IMAP_USER": "avigail@ula.example",
    }
    cli.main(
        [
            "daily",
            "--from-export",
            str(FIX / "emails"),
            "--state-dir",
            str(state_dir),
            "--out-dir",
            str(out_dir),
            "--as-of",
            "2026-06-05",
            "--dry-run",
        ],
        env=env,
    )
    # State unchanged: the existing project keeps its pre-run status.
    homepage = next(
        p
        for p in load_projects(state_dir / "projects.json")
        if p.project_id == "p-sprig-homepage"
    )
    assert homepage.status_agent == "active"
