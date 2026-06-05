"""apply_model_output — deterministic, guarded state merge (docs/05-model-seam.md).

The non-negotiable guard: apply writes only observed + agent-proposed columns and NEVER a
human-confirmed column. It also recomputes last_activity_date from evidence (not the model) and
matches model updates to existing projects so a model-coined id can't duplicate a known project.
"""

from digest_core.apply import apply_model_output
from digest_core.schema import ModelOutput
from digest_core.state import Project, Todo


def _projects():
    return [
        Project(
            project_id="p1",
            client_id="sprig",
            title="RhythMedix website",
            status="active",
            assignee="self",
            last_activity_date="2026-05-30",
        )
    ]


def test_updates_existing_project_agent_columns():
    out = ModelOutput.from_dict(
        {
            "project_updates": [
                {
                    "project_id": "p1",
                    "status_agent": "blocked",
                    "status_evidence": "client delayed copy (t-1)",
                    "confidence": "high",
                    "evidence_thread_ids": ["t-1"],
                    "todos": [],
                }
            ]
        }
    )
    projects = apply_model_output(
        _projects(), out, run_date="2026-06-05", thread_dates={"t-1": "2026-06-04"}
    )
    p = projects[0]
    assert p.status_agent == "blocked"
    assert p.status == "blocked"  # agent drives lifecycle when no human override
    assert p.confidence == "high"
    assert "t-1" in p.evidence_thread_ids
    assert p.last_seen_run == "2026-06-05"


def test_never_writes_human_confirmed_columns():
    out = ModelOutput.from_dict(
        {"project_updates": [{"project_id": "p1", "status_agent": "done"}]}
    )
    projects = apply_model_output(_projects(), out, run_date="2026-06-05")
    assert projects[0].status_confirmed is None
    assert projects[0].confirmed_note is None


def test_human_override_outranks_agent():
    projs = _projects()
    projs[0].status_confirmed = "on_hold"  # Avigail's manual override
    out = ModelOutput.from_dict(
        {"project_updates": [{"project_id": "p1", "status_agent": "active"}]}
    )
    projects = apply_model_output(projs, out, run_date="2026-06-05")
    assert projects[0].status_agent == "active"  # agent read still recorded
    assert (
        projects[0].status == "on_hold"
    )  # but confirmed status wins for the effective lifecycle


def test_last_activity_recomputed_from_evidence_not_model():
    out = ModelOutput.from_dict(
        {
            "project_updates": [
                {
                    "project_id": "p1",
                    "status_agent": "active",
                    "evidence_thread_ids": ["t-1"],
                }
            ]
        }
    )
    projects = apply_model_output(
        _projects(), out, run_date="2026-06-05", thread_dates={"t-1": "2026-06-04"}
    )
    assert projects[0].last_activity_date == "2026-06-04"  # advanced from evidence


def test_last_activity_never_regresses():
    out = ModelOutput.from_dict(
        {
            "project_updates": [
                {
                    "project_id": "p1",
                    "status_agent": "active",
                    "evidence_thread_ids": ["t-old"],
                }
            ]
        }
    )
    projects = apply_model_output(
        _projects(), out, run_date="2026-06-05", thread_dates={"t-old": "2026-01-01"}
    )
    assert (
        projects[0].last_activity_date == "2026-05-30"
    )  # keeps the later existing date


def test_new_project_created():
    out = ModelOutput.from_dict(
        {
            "project_updates": [
                {
                    "project_id": None,
                    "client_id": "ivory",
                    "title": "Brand refresh",
                    "status_agent": "active",
                    "todos": [],
                }
            ]
        }
    )
    projects = apply_model_output(_projects(), out, run_date="2026-06-05")
    assert len(projects) == 2
    new = [p for p in projects if p.client_id == "ivory"][0]
    assert new.title == "Brand refresh"
    assert new.status == "active"
    assert new.project_id  # got a deterministic slug id


def test_model_coined_id_matches_existing_by_title_no_duplicate():
    # Model invents a fresh id but the client+title clearly match p1 — must update, not duplicate.
    out = ModelOutput.from_dict(
        {
            "project_updates": [
                {
                    "project_id": "sprig-rhythmedix-website-2",
                    "client_id": "sprig",
                    "title": "RhythMedix website",
                    "status_agent": "done",
                }
            ]
        }
    )
    projects = apply_model_output(_projects(), out, run_date="2026-06-05")
    assert len(projects) == 1
    assert projects[0].project_id == "p1"
    assert projects[0].status_agent == "done"


def test_subset_title_does_not_wrongly_merge(tmp_path):
    # F5: "logo" must NOT fuzzy-merge into an existing "logo refresh" project for the same client.
    projs = [
        Project(
            project_id="p1", client_id="sprig", title="Logo refresh", status="active"
        )
    ]
    out = ModelOutput.from_dict(
        {
            "project_updates": [
                {
                    "project_id": None,
                    "client_id": "sprig",
                    "title": "Logo",
                    "status_agent": "active",
                }
            ]
        }
    )
    projects = apply_model_output(projs, out, run_date="2026-06-05")
    assert len(projects) == 2  # distinct project created, not merged


def test_shared_evidence_thread_matches_project():
    # F5: a shared evidence thread id is a strong same-project signal even with a different title.
    projs = [
        Project(
            project_id="p1",
            client_id="sprig",
            title="Homepage",
            status="active",
            evidence_thread_ids=["t-9"],
        )
    ]
    out = ModelOutput.from_dict(
        {
            "project_updates": [
                {
                    "project_id": None,
                    "client_id": "sprig",
                    "title": "Landing page",
                    "status_agent": "blocked",
                    "evidence_thread_ids": ["t-9"],
                }
            ]
        }
    )
    projects = apply_model_output(projs, out, run_date="2026-06-05")
    assert len(projects) == 1
    assert projects[0].status_agent == "blocked"


def _blocked_project():
    from digest_core.state import Blocker

    return [
        Project(
            project_id="p1",
            client_id="sprig",
            title="RhythMedix website",
            status="active",
            blockers=[Blocker("awaiting_consent", "approval", "2026-06-01")],
        )
    ]


def test_blockers_omitted_keeps_existing():
    # F6: an omitted blockers field means "no change", not "clear".
    out = ModelOutput.from_dict(
        {"project_updates": [{"project_id": "p1", "status_agent": "blocked"}]}
    )
    projects = apply_model_output(_blocked_project(), out, run_date="2026-06-05")
    assert len(projects[0].blockers) == 1


def test_blockers_empty_list_clears():
    # F6: an explicit [] means the model resolved the blockers.
    out = ModelOutput.from_dict(
        {
            "project_updates": [
                {"project_id": "p1", "status_agent": "active", "blockers": []}
            ]
        }
    )
    projects = apply_model_output(_blocked_project(), out, run_date="2026-06-05")
    assert projects[0].blockers == []


def test_expired_blocker_is_auto_cleared():
    from digest_core.state import Blocker

    projs = [
        Project(
            project_id="p1",
            client_id="sprig",
            title="X",
            status="blocked",
            blockers=[
                Blocker(
                    "awaiting_client_material",
                    "copy",
                    "2026-05-01",
                    blocks_until="2026-06-01",
                )
            ],
        )
    ]
    out = ModelOutput.from_dict(
        {"project_updates": [{"project_id": "p1", "status_agent": "blocked"}]}
    )
    projects = apply_model_output(
        projs, out, run_date="2026-06-05"
    )  # past blocks_until
    assert projects[0].blockers == []


def test_model_cannot_change_confirmed_value():
    # F10: a pre-set human-confirmed value must survive apply untouched.
    projs = _projects()
    projs[0].status_confirmed = "on_hold"
    projs[0].confirmed_note = "Avigail: paused per client call"
    out = ModelOutput.from_dict(
        {"project_updates": [{"project_id": "p1", "status_agent": "active"}]}
    )
    projects = apply_model_output(projs, out, run_date="2026-06-05")
    assert projects[0].status_confirmed == "on_hold"
    assert projects[0].confirmed_note == "Avigail: paused per client call"


def test_todos_carried_forward_when_model_omits_them():
    projs = _projects()
    projs[0].open_todos = [
        Todo(
            "chase client",
            "communicate_client",
            "agent@sprig.example",
            None,
            "blocking",
            "t-1",
        )
    ]
    out = ModelOutput.from_dict(
        {
            "project_updates": [
                {"project_id": "p1", "status_agent": "active", "todos": []}
            ]
        }
    )
    projects = apply_model_output(projs, out, run_date="2026-06-05")
    # Surface, don't drop: an unaddressed prior todo is not silently deleted.
    assert any(t.text == "chase client" for t in projects[0].open_todos)
