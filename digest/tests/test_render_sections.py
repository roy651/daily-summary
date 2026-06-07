"""Unresolved threads split into Personal / leads / entity-confirm / needs-your-eye sections, and the
editable todo file carries a parse-safe feedback template."""

import pytest

from digest_core.feedback import parse_todos_md
from digest_core.render import render_digest_md, render_todos_md
from digest_core.schema import ModelOutput


def test_digest_sections_reordered_and_folded():
    """Avigail's reshape: Updates → Todos → Status → Personal; needs-eye / entity / leads / suspected
    fold into Updates; bulk-marketing and the standalone unresolved boxes are gone."""
    from types import SimpleNamespace

    from digest_core.state import Project

    projects = [Project(project_id="rhythmedix-logo", client_id="sprig", title="logo")]
    out = ModelOutput.from_dict(
        {
            "digest_updates": [
                {
                    "project_id": "rhythmedix-logo",
                    "headline": "Assets received",
                    "detail": "from Katie",
                    "importance": "high",
                }
            ],
            "unresolved": [
                {"thread_id": "t1", "why": "TAU interview invite", "kind": "personal"},
                {"thread_id": "t2", "why": "Clutch cold lead", "kind": "lead"},
                {
                    "thread_id": "t3",
                    "why": "treating idan@rockdesign.co.il as a sub — confirm?",
                    "kind": "entity",
                },
                {"thread_id": "t4", "why": "unplaceable business thread"},
            ],
        }
    )
    suspected = [
        SimpleNamespace(
            kind="stale_todo",
            project_id="rhythmedix-logo",
            title="chase printer",
            detail="90d quiet",
        )
    ]
    md = render_digest_md(out, projects, run_date="2026-06-06", suspected=suspected)

    # 1) order: Email updates → Todos → Project status → Personal
    assert (
        md.index("## 📬 Email updates")
        < md.index("## ✅ Todos")
        < md.index("## 🗂 Project status")
        < md.index("## 👤 Personal")
    )
    # 2) each update line sits under a client+project mini-header
    assert "#### sprig — logo" in md and "Assets received" in md
    # 3) needs-eye / entity / non-spam lead / suspected-done all fold into Updates
    assert "**Also worth a look**" in md
    assert "unplaceable" in md and "idan@rockdesign.co.il" in md
    assert "possible lead" in md and "Clutch cold lead" in md
    assert "chase printer" in md and "likely done" in md
    # 4) the old standalone sections are gone
    for gone in (
        "## Possible new leads",
        "## New people / roles — confirm",
        "## Needs your eye",
        "## Suspected done",
        "Filtered as bulk/marketing",
    ):
        assert gone not in md
    # 5) personal mail stays, at the bottom
    assert "TAU interview" in md


def test_projectless_update_attaches_to_closest_project():
    """Double-down on the client+project prefix: an update the model left project-less is matched to its
    closest project by headline tokens, so it gets a real mini-header instead of a bare 'General'."""
    from digest_core.state import Project

    projects = [
        Project(
            project_id="rhythmedix-logo",
            client_id="sprig",
            end_client="rhythmedix",
            title="RhythMedix logo rebrand",
        ),
        Project(project_id="ivory-brand", client_id="ivory", title="Brand refresh"),
    ]
    out = ModelOutput.from_dict(
        {
            "digest_updates": [
                {
                    "headline": "Dana posted 3 logo variations for the RhythMedix rebrand",
                    "importance": "med",
                }  # no project_id
            ]
        }
    )
    md = render_digest_md(out, projects, run_date="2026-06-07")
    assert "#### sprig / rhythmedix — RhythMedix logo rebrand" in md
    assert "General" not in md


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


def test_state_review_folds_aliased_contacts_into_one_person():
    from digest_core.contacts import DigestContactStore
    from digest_core.render import render_state_review_md

    c = DigestContactStore()
    c.merge(
        ["idandamti@ula.co.il", "idan@rockdesign.co.il"],
        role="subcontractor",
        source="model",
        reason="same person",
    )
    md = render_state_review_md([], [], c)
    assert "idandamti@ula.co.il (aka idan@rockdesign.co.il)" in md
    assert (
        md.count("idan@rockdesign.co.il") == 1
    )  # alias shown only in the (aka …), not its own line


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
