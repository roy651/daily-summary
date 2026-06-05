"""Orchestration: run_bootstrap (cold start, holdout) + run_digest (daily) (docs/02-pipeline.md).

Driven offline with a ReplayReasoner so the whole pipeline runs end-to-end without a live model or
IMAP. The golden test exercises the same path through the CLI on .eml fixtures.
"""

import json
from datetime import datetime, timezone

from mail_evidence import Thread
from mail_evidence.records import EvidenceRecord

from digest_core.bootstrap import run_bootstrap
from digest_core.contacts import DigestContactStore
from digest_core.daily import run_digest
from digest_core.reasoner import ReplayReasoner
from digest_core.delivery import FileDelivery
from digest_core.state import ClientProfile, Project, load_projects

SELF = {"avigail@ula.example"}


def _email(mid, tid, day, from_, subject="hi", body="body"):
    return EvidenceRecord(
        id=mid,
        thread_id=tid,
        source="email",
        date=datetime(2026, 6, day, tzinfo=timezone.utc),
        body_text=body,
        from_=from_,
        to=["avigail@ula.example"],
        subject=subject,
    )


def _replay(tmp_path, output: dict) -> ReplayReasoner:
    path = tmp_path / "model_output.json"
    path.write_text(json.dumps(output))
    return ReplayReasoner(path)


# ── run_digest ──


def test_run_digest_end_to_end(tmp_path):
    projects = [
        Project(project_id="p1", client_id="sprig", title="Website", status="active")
    ]
    clients = [ClientProfile(client_id="sprig", display_name="SPRIG", is_agency=True)]
    contacts = DigestContactStore()
    contacts.add("agent@sprig.example", role="agent", source="bootstrap")
    threads = [
        Thread(
            thread_id="t-1",
            tier="T1",
            records=[_email("m1", "t-1", 5, "agent@sprig.example")],
        )
    ]

    reasoner = _replay(
        tmp_path,
        {
            "project_updates": [
                {
                    "project_id": "p1",
                    "status_agent": "blocked",
                    "status_evidence": "client asked to wait (t-1)",
                    "confidence": "high",
                    "evidence_thread_ids": ["t-1"],
                    "todos": [
                        {
                            "text": "chase client",
                            "category": "communicate_client",
                            "target": "agent@sprig.example",
                        }
                    ],
                }
            ],
            "digest_updates": [
                {"headline": "Client paused work", "detail": "", "importance": "high"}
            ],
        },
    )
    state_dir, out_dir = tmp_path / "state", tmp_path / "out"
    result = run_digest(
        projects=projects,
        clients=clients,
        contacts=contacts,
        threads=threads,
        reasoner=reasoner,
        delivery=FileDelivery(out_dir),
        run_date="2026-06-05",
        since="2026-06-04",
        self_addresses=SELF,
        state_dir=state_dir,
        out_dir=out_dir,
    )

    assert result.projects[0].status_agent == "blocked"
    assert result.projects[0].last_activity_date == "2026-06-05"  # from evidence
    assert (out_dir / "digest_2026-06-05.md").exists()
    # state persisted + reloads
    assert load_projects(state_dir / "projects.json")[0].status_agent == "blocked"


# ── run_bootstrap ──


def test_run_bootstrap_holds_out_recent_week_and_builds_map(tmp_path):
    records = [
        # Old (before holdout cutoff) — should seed the map.
        _email(
            "m1", "t-old", 1, "agent@sprig.example", subject="RhythMedix site brief"
        ),
        # Recent (inside the 7-day holdout window relative to 2026-06-10) — excluded.
        _email("m2", "t-new", 9, "newlead@fresh.example", subject="urgent new gig"),
    ]
    reasoner = _replay(
        tmp_path,
        {
            "project_updates": [
                {
                    "project_id": None,
                    "client_id": "sprig",
                    "end_client": "rhythmedix",
                    "title": "RhythMedix site",
                    "status_agent": "active",
                    "subcontractor": "dana@freelance.example",
                    "evidence_thread_ids": ["t-old"],
                    "todos": [
                        {
                            "text": "ask Avi about copy",
                            "category": "communicate_client",
                            "target": "agent@sprig.example",
                        }
                    ],
                }
            ]
        },
    )
    result = run_bootstrap(
        records=records,
        reasoner=reasoner,
        run_date="2026-06-10",
        holdout_days=7,
        self_addresses=SELF,
    )

    # Built a project from the old evidence.
    assert any(p.title == "RhythMedix site" for p in result.projects)
    # Derived a client stub.
    assert any(c.client_id == "sprig" for c in result.clients)
    # Reasoning-based promotion: only people the model tied to real work become contacts, with roles.
    # The agent is a communicate_client target on AGENCY work (end_client set) -> role "agent".
    assert result.contacts.role_of("agent@sprig.example") == "agent"
    assert result.contacts.role_of("dana@freelance.example") == "subcontractor"
    # A one-off inbound sender the model didn't attach to any work is NOT promoted (fixes N1 at root).
    assert not result.contacts.is_known("newlead@fresh.example")
    assert not result.contacts.is_known(
        "agent@sprig.example".replace("agent", "stranger")
    )
