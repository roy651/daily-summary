"""Regression tests for the two feedback bugs found in the first live file-delivery run:
(1) free-text corrections under the Feedback section were silently dropped (only `# notes:` was read);
(2) `# suppress:` was parsed but never applied. Plus feedback-note provenance marking."""

from digest_core.feedback import parse_todos_md
from digest_core.knowledge import KnowledgeStore
from digest_core.render import render_todos_md


def test_free_text_under_feedback_section_becomes_note():
    md = render_todos_md([], run_date="2026-06-06")
    md = md.replace("# suppress: ", "# suppress: T-SPAM")
    # Avigail types a plain-prose correction under the Feedback section, no `# notes:` prefix:
    md += "\nRock Design is Idan Damti, my web dev — same person, one subcontractor.\n"
    fb = parse_todos_md(md, run_date="2026-06-06")
    assert fb.suppressed_threads == ["T-SPAM"]
    assert "Rock Design is Idan Damti" in fb.freeform_notes
    assert (
        "finished/dormant project" not in fb.freeform_notes
    )  # help comment must not leak in


def test_note_singular_alias_is_accepted():
    fb = parse_todos_md("## ✎ Feedback\n# note: hello world\n", run_date="2026-06-06")
    assert "hello world" in fb.freeform_notes


def test_prose_outside_feedback_section_is_not_captured():
    # Todo lines / headers above the Feedback section must never be mistaken for notes.
    md = "# TODOs — 2026-06-06\n## Soon\n- [ ] [self] do a thing  (x) <!-- p1 -->\n"
    fb = parse_todos_md(md, run_date="2026-06-06")
    assert fb.freeform_notes == ""


def test_knowledge_marks_confirmed_notes():
    k = KnowledgeStore()
    k.add_general("an agent guess", date="2026-06-06", source="agent")
    k.add_general("Avigail's correction", date="2026-06-06", source="feedback")
    marked = k.general_notes(mark_confirmed=True)
    assert "an agent guess" in marked
    assert "[AVIGAIL-CONFIRMED] Avigail's correction" in marked
    # without the flag, no tagging (back-compat)
    assert "Avigail's correction" in k.general_notes()
