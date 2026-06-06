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


def test_state_review_lists_contacts_by_role():
    from digest_core.contacts import DigestContactStore
    from digest_core.render import render_state_review_md

    c = DigestContactStore()
    c.add(
        "idan@rockdesign.co.il",
        role="subcontractor",
        source="billing",
        reason="billing",
    )
    c.add("jen@sprigconsulting.com", role="agent", source="model")
    # A client WITH managing contacts guards against the `contacts` param being shadowed by the loop local.
    from digest_core.state import ClientProfile, ManagingContact

    clients = [
        ClientProfile(
            client_id="sprig",
            display_name="SPRIG",
            is_agency=True,
            managing_contacts=[
                ManagingContact(name="Jen", email="jen@sprigconsulting.com")
            ],
        )
    ]
    md = render_state_review_md(clients, [], c)
    assert "## Contacts & roles" in md
    assert "### subcontractor" in md and "idan@rockdesign.co.il" in md
    assert "### agent" in md and "jen@sprigconsulting.com" in md


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
    assert fb.corrections == []  # empty # forget:/# alias: placeholders are no-ops
