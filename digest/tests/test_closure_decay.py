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
    # Honest round-trip: render the editable file, check a line off, parse it back, close it.
    from digest_core.feedback import parse_todos_md
    from digest_core.render import render_todos_md

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
    md = render_todos_md(
        prioritize(projs, run_date="2026-05-18"), run_date="2026-05-18"
    )
    checked = md.replace(
        "- [ ] [self] Build the RMX BrandBook ",
        "- [x] [self] Build the RMX BrandBook ",
    )
    fb = parse_todos_md(checked, run_date="2026-05-18")
    closed = close_todos_from_feedback(projs, fb.eod_actuals)
    assert closed == 1
    assert [t.text for t in projs[0].open_todos] == ["Send Kristen the estimate"]


def test_feedback_closure_is_exact_not_substring():
    # G2: checking the longer todo must NOT silently close its shorter prefix-sibling.
    from digest_core.feedback import parse_todos_md
    from digest_core.render import render_todos_md

    projs = [
        Project(
            project_id="p1",
            client_id="acme",
            title="t",
            status="active",
            open_todos=[
                _todo("Send the brochure"),
                _todo("Send the brochure to the printer"),
            ],
        )
    ]
    md = render_todos_md(
        prioritize(projs, run_date="2026-05-18"), run_date="2026-05-18"
    )
    checked = md.replace(
        "- [ ] [self] Send the brochure to the printer",
        "- [x] [self] Send the brochure to the printer",
    )
    fb = parse_todos_md(checked, run_date="2026-05-18")
    closed = close_todos_from_feedback(projs, fb.eod_actuals)
    assert closed == 1
    assert [t.text for t in projs[0].open_todos] == [
        "Send the brochure"
    ]  # the shorter sibling survived


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


def test_new_window_evidence_advances_last_activity():
    # A project the model touches WITH evidence in this run's window advances to that evidence's date.
    projs = [
        Project(
            project_id="p1",
            client_id="c",
            title="t",
            status="active",
            last_activity_date="2026-03-01",
        )
    ]
    out = ModelOutput.from_dict(
        {
            "project_updates": [
                {
                    "project_id": "p1",
                    "status_agent": "active",
                    "evidence_thread_ids": ["th1"],
                }
            ]
        }
    )
    projects = apply_model_output(
        projs, out, run_date="2026-05-18", thread_dates={"th1": "2026-05-17"}
    )
    assert projects[0].last_activity_date == "2026-05-17"


def test_restated_project_without_new_evidence_does_not_reset_clock():
    # G1: a model re-stating an unchanged project (no evidence in THIS window) must NOT reset the decay
    # clock to run_date — otherwise dormancy/auto-archive could never fire under a re-stating model.
    projs = [
        Project(
            project_id="p1",
            client_id="c",
            title="Old project",
            status="active",
            last_activity_date="2026-03-01",
            evidence_thread_ids=["old-thread"],
        )
    ]
    out = ModelOutput.from_dict(
        {
            "project_updates": [
                {
                    "project_id": "p1",
                    "status_agent": "active",
                    "evidence_thread_ids": ["old-thread"],  # echoed; not in this window
                }
            ]
        }
    )
    projects = apply_model_output(
        projs, out, run_date="2026-05-18", thread_dates={"new-thread": "2026-05-18"}
    )
    assert projects[0].last_activity_date == "2026-03-01"  # aged, not reset
    s = suspected_closures(projects, run_date="2026-05-18")
    assert any(x.kind == "dormant_project" and x.project_id == "p1" for x in s)


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


# ── invoice-based reversible project closure ──


def test_billed_plus_silence_auto_archives():
    from digest_core.todos import auto_archive_billed

    projs = [
        Project(
            project_id="p1",
            client_id="c",
            title="t",
            status="active",
            last_activity_date="2026-05-01",
            billed_on="2026-05-01",
        )
    ]
    archived = auto_archive_billed(
        projs, run_date="2026-05-18", silent_days=7
    )  # silent 17d
    assert archived == ["p1"] and projs[0].status == "archived"


def test_billed_but_recent_not_archived():
    from digest_core.todos import auto_archive_billed

    projs = [
        Project(
            project_id="p1",
            client_id="c",
            title="t",
            status="active",
            last_activity_date="2026-05-16",
            billed_on="2026-05-16",
        )
    ]
    assert (
        auto_archive_billed(projs, run_date="2026-05-18", silent_days=7) == []
    )  # only 2d silent


def test_human_confirmed_active_not_auto_archived():
    from digest_core.todos import auto_archive_billed

    projs = [
        Project(
            project_id="p1",
            client_id="c",
            title="t",
            status="active",
            status_confirmed="active",
            last_activity_date="2026-05-01",
            billed_on="2026-05-01",
        )
    ]
    assert auto_archive_billed(projs, run_date="2026-05-18") == []


def test_billed_flag_sets_billed_on_and_revival_clears_it():
    # Model flags billed -> billed_on set.
    projs = [Project(project_id="p1", client_id="c", title="t", status="active")]
    projs = apply_model_output(
        projs,
        ModelOutput.from_dict(
            {
                "project_updates": [
                    {
                        "project_id": "p1",
                        "status_agent": "active",
                        "billed": True,
                        "evidence_thread_ids": ["b1"],
                    }
                ]
            }
        ),
        run_date="2026-05-01",
        thread_dates={"b1": "2026-05-01"},
    )
    assert projs[0].billed_on == "2026-05-01"
    # It then archives on silence...
    from digest_core.todos import auto_archive_billed

    auto_archive_billed(projs, run_date="2026-05-18")
    assert projs[0].status == "archived"
    # ...and a NEW item revives it (status active) and clears the billing cycle.
    projs = apply_model_output(
        projs,
        ModelOutput.from_dict(
            {"project_updates": [{"project_id": "p1", "status_agent": "active"}]}
        ),
        run_date="2026-05-20",
    )
    assert projs[0].status == "active" and projs[0].billed_on is None


def test_feedback_archive_and_revive_directives():
    from digest_core.feedback import parse_reply

    fb = parse_reply("archive: p1 p2\nrevive: p3", run_date="2026-05-18")
    assert fb.archived_projects == ["p1", "p2"]
    assert fb.revived_projects == ["p3"]
