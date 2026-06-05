"""TODO prioritization + carry-forward merge (docs/03-todo-model.md).

Priority is deterministic (model proposes, Python ranks) from deadline pressure, blocker leverage,
and staleness. Tests assert band assignment and relative ordering rather than exact scores, so the
scoring can be tuned without churn.
"""

from digest_core.state import Blocker, Project, Task, Todo
from digest_core.todos import merge_todos, prioritize


def _todo(text, category="self", target=None, due_hint=None):
    return Todo(
        text=text,
        category=category,
        target=target,
        due_hint=due_hint,
        rationale="",
        source_thread_id=None,
    )


def _project(pid, **over):
    base = dict(
        project_id=pid,
        client_id="sprig",
        title=f"Project {pid}",
        status="active",
        assignee="self",
    )
    base.update(over)
    return Project(**base)


# ── prioritize: banding ──


def test_hard_deadline_tomorrow_is_urgent():
    p = _project(
        "p1", deadline="2026-06-06", deadline_kind="hard", open_todos=[_todo("ship it")]
    )
    ranked = prioritize([p], run_date="2026-06-05")
    assert ranked[0].band == "urgent"


def test_no_deadline_fresh_unblocked_is_whenever():
    p = _project(
        "p1", last_activity_date="2026-06-05", open_todos=[_todo("tidy assets")]
    )
    ranked = prioritize([p], run_date="2026-06-05")
    assert ranked[0].band == "whenever"


# ── prioritize: ordering ──


def test_unblocking_action_outranks_self_action():
    blocked = _project(
        "p1",
        status="blocked",
        blockers=[Blocker("awaiting_client_material", "copy", "2026-06-01")],
        last_activity_date="2026-06-04",
        open_todos=[
            _todo(
                "chase client for copy",
                category="communicate_client",
                target="agent@sprig.example",
            )
        ],
    )
    active = _project(
        "p2", last_activity_date="2026-06-04", open_todos=[_todo("polish mockup")]
    )
    ranked = prioritize([active, blocked], run_date="2026-06-05")
    order = [r.todo.text for r in ranked]
    assert order.index("chase client for copy") < order.index("polish mockup")


def test_stale_project_escalates_over_fresh():
    stale = _project(
        "p1",
        last_activity_date="2026-05-16",
        open_todos=[_todo("follow up old thread")],
    )
    fresh = _project(
        "p2", last_activity_date="2026-06-04", open_todos=[_todo("recent task")]
    )
    ranked = prioritize([fresh, stale], run_date="2026-06-05")
    order = [r.todo.text for r in ranked]
    assert order.index("follow up old thread") < order.index("recent task")


def test_includes_task_level_todos():
    p = _project(
        "p1",
        open_todos=[_todo("project-level")],
        tasks=[
            Task(
                task_id="t1",
                title="Logo",
                status="active",
                owner="self",
                open_todos=[_todo("task-level")],
            )
        ],
    )
    texts = {r.todo.text for r in prioritize([p], run_date="2026-06-05")}
    assert texts == {"project-level", "task-level"}


def test_deterministic_tie_break_by_project_id():
    a = _project("zeta", last_activity_date="2026-06-05", open_todos=[_todo("x")])
    b = _project("alpha", last_activity_date="2026-06-05", open_todos=[_todo("x")])
    ranked = prioritize([a, b], run_date="2026-06-05")
    # Equal scores -> ordered by project_id ascending.
    assert [r.project_id for r in ranked] == ["alpha", "zeta"]


# ── carry-forward merge ──


def test_merge_proposed_replaces_matching_prior():
    prior = [_todo("Chase client for copy")]
    proposed = [
        _todo(
            "chase client for copy",
            category="communicate_client",
            target="agent@sprig.example",
        )
    ]
    merged = merge_todos(prior, proposed)
    assert len(merged) == 1
    assert merged[0].category == "communicate_client"  # the proposed version won


def test_merge_carries_unaddressed_prior():
    prior = [_todo("old unaddressed action")]
    proposed = [_todo("new action")]
    merged = merge_todos(prior, proposed)
    assert [t.text for t in merged] == ["new action", "old unaddressed action"]
