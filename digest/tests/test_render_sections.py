"""Unresolved threads split into Personal / leads / entity-confirm / needs-your-eye sections, and the
editable todo file carries a parse-safe feedback template."""

import pytest

from digest_core.feedback import parse_todos_md
from digest_core.render import render_digest_md, render_todos_md
from digest_core.schema import ModelOutput


def test_unresolved_splits_into_sections():
    out = ModelOutput.from_dict(
        {
            "project_updates": [],
            "digest_updates": [],
            "insights": [],
            "unresolved": [
                {"thread_id": "t1", "why": "TAU interview invite", "kind": "personal"},
                {"thread_id": "t2", "why": "Clutch cold lead", "kind": "lead"},
                {
                    "thread_id": "t3",
                    "why": "treating idan@rockdesign.co.il as a sub — confirm?",
                    "kind": "entity",
                },
                {
                    "thread_id": "t4",
                    "why": "unplaceable business thread",
                },  # default kind
            ],
        }
    )
    md = render_digest_md(out, [], run_date="2026-06-06")
    assert "## Personal" in md and "TAU interview" in md
    assert "## Possible new leads" in md
    assert "## New people / roles — confirm" in md and "idan@rockdesign.co.il" in md
    assert "## Needs your eye" in md and "unplaceable" in md


def test_unresolved_kind_defaults_and_validates():
    assert (
        ModelOutput.from_dict({"unresolved": [{"thread_id": "t"}]}).unresolved[0].kind
        == "unplaced"
    )
    with pytest.raises(ValueError):
        ModelOutput.from_dict({"unresolved": [{"thread_id": "t", "kind": "bogus"}]})


def test_todos_feedback_template_is_parse_safe():
    md = render_todos_md([], run_date="2026-06-06")
    assert "✎ Feedback" in md and "# notes:" in md and "# archive:" in md
    # empty placeholders must round-trip to NO directives (no accidental closures/archives)
    fb = parse_todos_md(md, run_date="2026-06-06")
    assert fb.archived_projects == []
    assert fb.revived_projects == []
    assert fb.suppressed_threads == []
    assert fb.freeform_notes == ""
    assert fb.eod_actuals == []
