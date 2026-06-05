"""Closure + decay — the 'remove' half of the system (Review-3 D0).

Three inputs, one safety valve: evidence-based closure (model closes todos / marks done), feedback
closure (Avigail's check-offs), passive decay (staleness -> suspected, surfaced not deleted). Plus
the D1 fix (overdue deadlines no longer score as Urgent).
"""

from digest_core.apply import apply_model_output
from digest_core.schema import ModelOutput
from digest_core.state import Project, Todo
from digest_core.todos import (
    close_todos_from_feedback,
    prioritize,
    suspected_closures,
)


def _todo(text, category="self", due_hint=None):
    return Todo(
        text=text,
        category=category,
        target=None,
        due_hint=due_hint,
        rationale="",
        source_thread_id=None,
    )


# ── evidence-based closure (model) ──


def test_model_closes_todos_by_text():
    projs = [
        Project(
            project_id="p1",
            client_id="c",
            title="t",
            status="active",
            open_todos=[_todo("Prepare print files"), _todo("Chase client")],
        )
    ]
    out = ModelOutput.from_dict(
        {
            "project_updates": [
                {"project_id": "p1", "closed_todos": ["prepare print files"]}
            ]
        }
    )
    projects = apply_model_output(projs, out, run_date="2026-05-18")
    texts = [t.text for t in projects[0].open_todos]
    assert texts == [
        "Chase client"
    ]  # the completed one was removed, the other carried forward


def test_model_marks_project_done_drops_from_active():
    projs = [Project(project_id="p1", client_id="c", title="t", status="active")]
    out = ModelOutput.from_dict(
        {"project_updates": [{"project_id": "p1", "status_agent": "done"}]}
    )
    projects = apply_model_output(projs, out, run_date="2026-05-18")
    assert projects[0].status == "done"  # render hides done from the active status list


# ── feedback closure (Avigail's check-offs) ──


def test_feedback_checkoffs_close_todos():
    projs = [
        Project(
            project_id="p1",
            client_id="c",
            title="t",
            status="active",
            open_todos=[
                _todo("Build the RMX BrandBook"),
                _todo("Send Kristen the estimate"),
            ],
        )
    ]
    # The rendered+checked line contains the todo text plus tags/markers.
    done_items = ["[self] Build the RMX BrandBook from elements  (sprig / rhythmedix)"]
    closed = close_todos_from_feedback(projs, done_items)
    assert (
        closed == 0 or closed == 1
    )  # substring match: "Build the RMX BrandBook" is in the line
    assert any(t.text == "Send Kristen the estimate" for t in projs[0].open_todos)
    assert not any(t.text == "Build the RMX BrandBook" for t in projs[0].open_todos)


# ── passive decay (surface, never delete) ──


def test_dormant_project_is_suspected_not_deleted():
    projs = [
        Project(
            project_id="p1",
            client_id="c",
            title="Old project",
            status="active",
            last_activity_date="2026-04-01",
        ),
        Project(
            project_id="p2",
            client_id="c",
            title="Fresh",
            status="active",
            last_activity_date="2026-05-17",
        ),
    ]
    s = suspected_closures(projs, run_date="2026-05-18", dormant_after_days=28)
    dormant = [x for x in s if x.kind == "dormant_project"]
    assert [d.project_id for d in dormant] == ["p1"]  # silent ~47 days
    assert len(projs) == 2  # nothing deleted


def test_overdue_todo_on_stale_project_is_suspected_done():
    projs = [
        Project(
            project_id="p1",
            client_id="c",
            title="t",
            status="active",
            last_activity_date="2026-03-01",  # project also gone quiet
            open_todos=[_todo("Ship the booth", due_hint="2026-04-01")],
        )
    ]
    s = suspected_closures(projs, run_date="2026-05-18")
    assert any(x.kind == "overdue_todo" and "Ship the booth" in x.title for x in s)


def test_overdue_todo_on_fresh_project_is_not_suspected():
    # Just-overdue on an actively-worked project is genuinely due-now, not a completion to confirm.
    projs = [
        Project(
            project_id="p1",
            client_id="c",
            title="t",
            status="active",
            last_activity_date="2026-05-18",  # fresh
            open_todos=[_todo("Fix the typo and launch", due_hint="2026-05-17")],
        )
    ]
    s = suspected_closures(projs, run_date="2026-05-18")
    assert not any(x.kind == "overdue_todo" for x in s)


# ── D1: overdue deadline is NOT urgent ──


def test_overdue_deadline_not_urgent():
    projs = [
        Project(
            project_id="p1",
            client_id="c",
            title="t",
            status="active",
            last_activity_date="2026-05-18",
            deadline="2026-04-01",
            deadline_kind="hard",
            open_todos=[_todo("overdue thing")],
        )
    ]
    ranked = prioritize(projs, run_date="2026-05-18")
    assert ranked[0].band != "urgent"  # past hard deadline no longer inflates to Urgent
