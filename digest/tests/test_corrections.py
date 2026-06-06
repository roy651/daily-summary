"""Correction mechanism — retract false knowledge + merge mis-identified contacts, driven by either
Avigail's feedback or the reasoner itself (so false facts don't linger; the Idan/Rock-Design case)."""

import pytest

from digest_core.apply import apply_corrections
from digest_core.contacts import DigestContactStore
from digest_core.feedback import parse_reply, parse_todos_md
from digest_core.knowledge import KnowledgeStore
from digest_core.schema import Correction, ModelOutput


def _knowledge(notes):
    k = KnowledgeStore()
    for n in notes:
        k.add_general(n, date="2026-01-01", source="agent")
    return k


def test_knowledge_supersede_removes_then_replaces():
    k = _knowledge(["Rock Design is a vendor, distinct from Idan Damti", "keep me"])
    removed = k.supersede(
        "distinct from idan damti",
        note="Rock Design is Idan Damti (one person).",
        date="2026-06-06",
        source="feedback",
    )
    notes = k.general_notes()
    assert removed == 1
    assert not any("distinct" in n for n in notes)
    assert any("one person" in n for n in notes)
    assert any("keep me" in n for n in notes)  # unrelated note untouched


def test_contacts_set_role_forces_but_human_outranks_model():
    c = DigestContactStore()
    c.add("idan@rockdesign.co.il", role="other", source="auto")
    c.set_role("idan@rockdesign.co.il", role="subcontractor", source="model")
    assert c.role_of("idan@rockdesign.co.il") == "subcontractor"  # model corrects auto
    c.set_role("idan@rockdesign.co.il", role="client", source="feedback")  # human wins
    c.set_role("idan@rockdesign.co.il", role="agent", source="model")  # blocked
    assert c.role_of("idan@rockdesign.co.il") == "client"


def test_apply_corrections_retract_and_merge():
    k = _knowledge(["Rock Design is distinct from Idan Damti"])
    c = DigestContactStore()
    apply_corrections(
        [
            Correction(
                kind="retract_knowledge",
                match="distinct from Idan Damti",
                note="Rock Design = Idan Damti, one web-dev subcontractor.",
            ),
            Correction(
                kind="merge_contacts",
                emails=["idan@rockdesign.co.il", "idandamti@ula.co.il"],
                role="subcontractor",
            ),
        ],
        k,
        c,
        run_date="2026-06-06",
        source="feedback",
    )
    assert not any("distinct" in n for n in k.general_notes())
    assert any("one web-dev subcontractor" in n for n in k.general_notes())
    assert c.role_of("idan@rockdesign.co.il") == "subcontractor"
    assert c.role_of("idandamti@ula.co.il") == "subcontractor"


def test_feedback_parses_forget_and_alias_from_todos():
    md = (
        "## ✎ Feedback\n"
        "# forget: Rock Design is a separate vendor\n"
        "# alias: idan@rockdesign.co.il, idandamti@ula.co.il = subcontractor\n"
    )
    fb = parse_todos_md(md, run_date="2026-06-06")
    assert {x.kind for x in fb.corrections} == {"retract_knowledge", "merge_contacts"}
    merge = next(x for x in fb.corrections if x.kind == "merge_contacts")
    assert merge.emails == ["idan@rockdesign.co.il", "idandamti@ula.co.il"]
    assert merge.role == "subcontractor"


def test_feedback_parses_forget_and_alias_from_email_reply():
    fb = parse_reply(
        "forget: Rock Design is a vendor\nalias: a@x.com b@y.com = subcontractor\n",
        run_date="2026-06-06",
    )
    assert any(x.kind == "retract_knowledge" for x in fb.corrections)
    merge = next(x for x in fb.corrections if x.kind == "merge_contacts")
    assert merge.emails == ["a@x.com", "b@y.com"] and merge.role == "subcontractor"


def test_model_output_corrections_parse_and_validate():
    o = ModelOutput.from_dict(
        {"corrections": [{"kind": "retract_knowledge", "match": "x"}]}
    )
    assert o.corrections[0].kind == "retract_knowledge"
    with pytest.raises(ValueError):
        ModelOutput.from_dict({"corrections": [{"kind": "bogus"}]})
