"""Digest + todo-file rendering (docs/02). Pure formatting; deterministic output.

Asserts the three digest sections (project status / important updates / prioritized todos), the
"needs your eye" surfacing of unresolved threads, and that the todo file is editable with a
machine-readable project marker for feedback round-trip.
"""

from digest_core.render import render_digest_md, render_todos_md
from digest_core.schema import ModelOutput
from digest_core.state import Project, Todo
from digest_core.todos import prioritize


def _projects():
    return [
        Project(
            project_id="p1",
            client_id="sprig",
            end_client="rhythmedix",
            title="Website redesign",
            status="blocked",
            status_reason="awaiting copy",
            confidence="high",
            deadline="2026-06-06",
            deadline_kind="hard",
            open_todos=[
                Todo(
                    "Chase client for copy",
                    "communicate_client",
                    "agent@sprig.example",
                    "2026-06-06",
                    "blocking",
                    "t-1",
                )
            ],
        ),
        Project(
            project_id="p2",
            client_id="ivory",
            title="Brand refresh",
            status="active",
            last_activity_date="2026-06-05",
            open_todos=[Todo("Draft moodboard", "self", None, None, "kickoff", "t-2")],
        ),
    ]


def _output():
    return ModelOutput.from_dict(
        {
            "digest_updates": [
                {
                    "project_id": "p1",
                    "headline": "Client delayed copy",
                    "detail": "by a week",
                    "importance": "high",
                },
                {
                    "project_id": "p2",
                    "headline": "New brand kickoff",
                    "detail": "starts Monday",
                    "importance": "med",
                },
            ],
            "unresolved": [
                {"thread_id": "t-9", "why": "unknown sender, possibly a new lead"}
            ],
        }
    )


def test_digest_has_three_sections_and_unresolved():
    md = render_digest_md(
        _output(), _projects(), run_date="2026-06-05", run_date_label="2026-06-05"
    )
    assert "# Daily digest" in md
    assert "## 📬 Email updates" in md
    assert "## ✅ Todos" in md
    assert "## 🗂 Project status" in md
    # an unplaced thread folds into "Also worth a look" under Updates (no standalone section)
    assert "**Also worth a look**" in md
    # content surfaces
    assert "Website redesign" in md
    assert "Client delayed copy" in md
    assert (
        "possibly a new lead" in md
    )  # the unplaced thread folds into "Also worth a look" (no raw id)


def test_digest_todos_ranked_urgent_first():
    projects = _projects()
    md = render_digest_md(
        _output(), projects, run_date="2026-06-05", run_date_label="2026-06-05"
    )
    # The hard-deadline-tomorrow chase must appear before the no-deadline moodboard.
    assert md.index("Chase client for copy") < md.index("Draft moodboard")


def test_todos_file_is_editable_with_marker():
    ranked = prioritize(_projects(), run_date="2026-06-05")
    md = render_todos_md(ranked, run_date="2026-06-05")
    assert "- [ ]" in md  # editable checkboxes
    assert "p1" in md  # machine-readable project marker for feedback round-trip
    assert "Chase client for copy" in md


def test_render_is_deterministic():
    a = render_digest_md(
        _output(), _projects(), run_date="2026-06-05", run_date_label="2026-06-05"
    )
    b = render_digest_md(
        _output(), _projects(), run_date="2026-06-05", run_date_label="2026-06-05"
    )
    assert a == b
