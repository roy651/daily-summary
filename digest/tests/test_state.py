"""State model: dataclasses + JSON round-trip (docs/01-state-model.md).

The round-trip invariant is the contract everything else relies on: a written file re-loads to an
equal object graph, None<->null preserved, stable key order. We also pin the three-way separation
(observed / agent-proposed / human-confirmed) and the Project->Task->Todo hierarchy.
"""

import json

import pytest

from digest_core.state import (
    Blocker,
    ClientProfile,
    ManagingContact,
    Observation,
    Project,
    Task,
    Todo,
    load_clients,
    load_projects,
    write_clients,
    write_projects,
)


def _full_project() -> Project:
    """A project exercising every nested shape: task, blocker, todos at both levels, observations."""
    return Project(
        project_id="sprig-rhythmedix-site",
        client_id="sprig",
        end_client="rhythmedix",
        title="RhythMedix website redesign",
        description="Full redesign of the marketing site.",
        assignee="subcontractor",
        subcontractor="dana@example.com",
        contact_channel="agent",
        status="blocked",
        status_reason="awaiting copy from the client",
        deadline="2026-06-20",
        deadline_kind="hard",
        blockers=[
            Blocker(
                kind="awaiting_client_material",
                description="final homepage copy",
                since="2026-05-30",
                blocks_until=None,
            )
        ],
        last_activity_date="2026-06-02",
        last_seen_run="2026-06-05",
        status_agent="blocked",
        status_evidence="client said copy is delayed (thread t-1)",
        confidence="high",
        evidence_thread_ids=["t-1", "t-2"],
        status_confirmed=None,
        confirmed_note=None,
        tasks=[
            Task(
                task_id="homepage",
                title="Homepage mockup",
                status="active",
                owner="self",
                subcontractor=None,
                deadline="2026-06-12",
                blockers=[],
                open_todos=[
                    Todo(
                        text="Send homepage mockup v2 to the SPRIG agent",
                        category="communicate_client",
                        target="agent@sprig.example",
                        due_hint="2026-06-06",
                        rationale="agent asked for v2 in thread t-2",
                        source_thread_id="t-2",
                    )
                ],
                observations=[
                    Observation(
                        date="2026-06-01", source="email", note="client likes blue"
                    )
                ],
            )
        ],
        open_todos=[
            Todo(
                text="Chase client for final copy",
                category="communicate_client",
                target="agent@sprig.example",
                due_hint=None,
                rationale="blocking the whole project",
                source_thread_id="t-1",
            )
        ],
        observations=[
            Observation(
                date="2026-05-30", source="email", note="tight timeline overall"
            )
        ],
        notes="biggest active SPRIG job",
    )


def test_project_round_trip(tmp_path):
    projects = [_full_project()]
    path = tmp_path / "projects.json"
    write_projects(projects, path)

    reloaded = load_projects(path)

    assert reloaded == projects


def test_client_round_trip(tmp_path):
    clients = [
        ClientProfile(
            client_id="sprig",
            display_name="SPRIG",
            is_agency=True,
            language="en",
            status="active",
            managing_contacts=[
                ManagingContact(
                    name="Avi", email="agent@sprig.example", role_note="my main agent"
                )
            ],
            observations=[
                Observation(date="2026-05-01", source="manual", note="pays on time")
            ],
            notes="agency: invoices split per end-client",
        ),
        ClientProfile(
            client_id="ivory",
            display_name="Ivory",
            is_agency=False,
            language="he",
            status="archived",
            managing_contacts=[],
            observations=[],
            notes="",
        ),
    ]
    path = tmp_path / "clients.json"
    write_clients(clients, path)

    assert load_clients(path) == clients


def test_none_preserved_not_dropped(tmp_path):
    """None must serialize as JSON null and reload as None (not absent, not '')."""
    p = _full_project()
    p.deadline = None
    p.deadline_kind = None
    path = tmp_path / "projects.json"
    write_projects([p], path)

    raw = json.loads(path.read_text())
    assert raw[0]["deadline"] is None
    assert raw[0]["deadline_kind"] is None
    assert load_projects(path)[0].deadline is None


def test_written_json_is_stable_and_pretty(tmp_path):
    """Stable key order + indentation so git diffs of state are reviewable."""
    path = tmp_path / "projects.json"
    write_projects([_full_project()], path)
    first = path.read_text()

    # Re-writing the reloaded object produces byte-identical output (deterministic ordering).
    write_projects(load_projects(path), path)
    assert path.read_text() == first
    assert first.endswith("\n")
    assert "  " in first  # indented, not a single line


def test_empty_collections_round_trip(tmp_path):
    path = tmp_path / "projects.json"
    write_projects([], path)
    assert load_projects(path) == []


def test_todo_category_is_validated():
    """Categories are an extensible-but-checked enum; an unknown value is rejected at construction."""
    with pytest.raises(ValueError):
        Todo(
            text="bad",
            category="not_a_category",
            target=None,
            due_hint=None,
            rationale="",
            source_thread_id=None,
        )
