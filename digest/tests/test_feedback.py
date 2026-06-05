"""Feedback parser — the captured-but-not-consumed channel (docs/04-delivery.md).

v1 builds the channel + schema and persists records; consuming feedback into reasoning is phase 2.
We parse the edited todo file (checkboxes) and an email reply body (directives).
"""

from digest_core.feedback import FeedbackRecord, parse_reply, parse_todos_md

EDITED_TODOS = """# TODOs — 2026-06-05
## Urgent
- [x] [communicate_client] Chase client for copy → agent@sprig.example  (sprig / rhythmedix) <!-- p1 -->
- [ ] [self] Draft moodboard  (ivory) <!-- p2 -->
# suppress: t-9 t-12
# notes: skip the Verge thread, it's spam
"""


def test_parse_todos_md_splits_done_and_open():
    fb = parse_todos_md(EDITED_TODOS, run_date="2026-06-05")
    assert any("Chase client for copy" in t for t in fb.eod_actuals)
    assert any("Draft moodboard" in t for t in fb.revised_todos)


def test_parse_todos_md_collects_suppressions_and_notes():
    fb = parse_todos_md(EDITED_TODOS, run_date="2026-06-05")
    assert set(fb.suppressed_threads) == {"t-9", "t-12"}
    assert "spam" in fb.freeform_notes


def test_parse_reply_extracts_directives():
    body = "done: sent the logo\nsuppress: t-3\nactually push the RhythMedix deadline to next week"
    fb = parse_reply(body, run_date="2026-06-05")
    assert any("sent the logo" in t for t in fb.eod_actuals)
    assert "t-3" in fb.suppressed_threads
    assert "push the RhythMedix deadline" in fb.freeform_notes


def test_feedback_record_round_trip(tmp_path):
    fb = FeedbackRecord(
        run_date="2026-06-05",
        revised_todos=["a"],
        eod_actuals=["b"],
        suppressed_threads=["t-9"],
        freeform_notes="note",
    )
    path = tmp_path / "feedback_2026-06-05.json"
    fb.save(path)
    assert FeedbackRecord.load(path) == fb
