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


def test_knowledge_containment_dedup():
    k = KnowledgeStore()
    k.add_general("Idan is the web dev", date="d", source="agent")
    k.add_general("Idan is the web dev", date="d", source="feedback")  # exact -> skip
    assert len(k.general) == 1
    k.add_general(
        "Idan is the web dev for SPRIG", date="d", source="agent"
    )  # superset -> replace
    assert len(k.general) == 1 and "SPRIG" in k.general_notes()[0]
    k.add_general(
        "Idan is the web dev", date="d", source="agent"
    )  # now contained -> skip
    assert len(k.general) == 1
    k.add_general(
        "Nurit is an illustrator", date="d", source="agent"
    )  # distinct -> kept
    assert len(k.general) == 2


def test_contacts_set_role_forces_but_human_outranks_model():
    c = DigestContactStore()
    c.add("idan@rockdesign.co.il", role="other", source="auto")
    c.set_role("idan@rockdesign.co.il", role="subcontractor", source="model")
    assert c.role_of("idan@rockdesign.co.il") == "subcontractor"  # model corrects auto
    c.set_role("idan@rockdesign.co.il", role="client", source="feedback")  # human wins
    c.set_role("idan@rockdesign.co.il", role="agent", source="model")  # blocked
    assert c.role_of("idan@rockdesign.co.il") == "client"


def test_merge_links_aliases_to_canonical_with_shared_role():
    c = DigestContactStore()
    c.add("idandamti@ula.co.il", role="other", source="auto")
    c.merge(
        ["idandamti@ula.co.il", "idan@rockdesign.co.il"],
        role="subcontractor",
        source="model",
        reason="same person",
    )
    assert c.role_of("idandamti@ula.co.il") == "subcontractor"
    assert c.role_of("idan@rockdesign.co.il") == "subcontractor"
    assert c.entry("idandamti@ula.co.il").alias_of is None  # canonical
    assert c.entry("idan@rockdesign.co.il").alias_of == "idandamti@ula.co.il"


def test_alias_survives_later_promotion_and_set_role():
    # Regression: a daily run re-promotes contacts via add()/set_role — the entity merge must NOT be lost.
    c = DigestContactStore()
    c.merge(
        ["idandamti@ula.co.il", "idan@rockdesign.co.il"],
        role="subcontractor",
        source="model",
        reason="same person",
    )
    c.add(
        "idan@rockdesign.co.il", role="subcontractor", source="model", reason="promoted"
    )
    assert c.entry("idan@rockdesign.co.il").alias_of == "idandamti@ula.co.il"
    c.set_role(
        "idan@rockdesign.co.il", role="subcontractor", source="billing", reason="x"
    )
    assert c.entry("idan@rockdesign.co.il").alias_of == "idandamti@ula.co.il"


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


# ── M1: knowledge store gains the same provenance guard the contact store has ──
# A model-sourced retract/replace must NOT destroy an Avigail-confirmed note (the inverse of the H2
# guarantee). Reuse SOURCE_RANK: a writer may only remove/replace notes its source outranks-or-equals.


def test_model_supersede_cannot_remove_confirmed_note():
    k = KnowledgeStore()
    k.add_general("Rock Design is a separate vendor", date="d", source="agent")
    k.add_general("Rock Design is Idan Damti, one person.", date="d", source="feedback")
    removed = k.supersede("rock design", date="2026-06-06", source="model")
    notes = k.general_notes()
    assert removed == 1  # only the agent note (model can't touch the confirmed one)
    assert not any("separate vendor" in n for n in notes)
    assert any("one person" in n for n in notes)  # confirmed survives a model retract


def test_feedback_supersede_removes_even_a_confirmed_note():
    k = KnowledgeStore()
    k.add_general("Rock Design is Idan", date="d", source="feedback")
    removed = k.supersede("rock design", date="2026-06-06", source="feedback")
    assert removed == 1 and not k.general_notes()  # human outranks anything


def test_model_superset_does_not_replace_confirmed_note():
    k = KnowledgeStore()
    k.add_general("Rock Design is Idan", date="d", source="feedback")
    # A richer model paraphrase must not silently drop the shorter confirmed note.
    k.add_general(
        "Rock Design is Idan Damti, the web dev for SPRIG", date="d", source="model"
    )
    assert any(
        o.note == "Rock Design is Idan" and o.source == "feedback" for o in k.general
    )


# ── M2: role_of resolves through alias_of so an alias's role never goes stale (J4) ──


def test_role_of_resolves_through_alias_after_canonical_set_role():
    c = DigestContactStore()
    c.merge(
        ["idandamti@ula.co.il", "idan@rockdesign.co.il"],
        role="subcontractor",
        source="model",
        reason="same person",
    )
    # A later authoritative correction on the canonical only — the alias must follow it.
    c.set_role("idandamti@ula.co.il", role="client", source="feedback")
    assert c.role_of("idan@rockdesign.co.il") == "client"


# ── M3: a forget/retract echoes what it removed (visible blast radius) ──


def test_supersede_logs_removed_notes(caplog):
    import logging

    k = KnowledgeStore()
    k.add_general("Rock Design is a separate vendor", date="d", source="agent")
    with caplog.at_level(logging.INFO, logger="digest.knowledge"):
        k.supersede("rock design", date="2026-06-06", source="feedback")
    assert any("separate vendor" in r.getMessage() for r in caplog.records)
