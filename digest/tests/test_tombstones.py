"""Tombstone foundation for the dashboard (docs/08): human-confirmed deletions are flags, not hard
deletes, so the cron re-deriving from the same evidence can't resurrect them. Stable content-ids let a
flag target the right item across regeneration."""

from digest_core.state import Observation, Todo, _content_id
from digest_core.todos import merge_todos, prioritize


def _todo(text, **kw):
    return Todo(
        text=text,
        category=kw.get("category", "self"),
        target=kw.get("target"),
        due_hint=kw.get("due_hint"),
        rationale=kw.get("rationale", ""),
        source_thread_id=kw.get("source_thread_id"),
        source=kw.get("source", "model"),
        done=kw.get("done", False),
    )


def test_content_id_is_deterministic_and_whitespace_stable():
    assert _content_id("Call Molly") == _content_id("  call   molly ")
    assert _content_id("Call Molly") != _content_id("Call Carla")
    # auto-assigned on construction
    assert _todo("Call Molly").id == _content_id("Call Molly")


def test_closed_todo_is_not_resurrected_by_a_model_reproposal():
    prior = [_todo("Chase Molly for the image", done=True)]
    proposed = [_todo("Chase Molly for the image")]  # model re-proposes the same action
    merged = merge_todos(prior, proposed)
    # exactly one, still the closed tombstone — the proposal did NOT bring it back
    matching = [t for t in merged if t.text == "Chase Molly for the image"]
    assert len(matching) == 1 and matching[0].done is True


def test_human_todo_is_not_overwritten_by_model():
    prior = [_todo("Send Carla the invoice", source="human")]
    proposed = [
        _todo("Send Carla the invoice", source="model", rationale="model wording")
    ]
    merged = merge_todos(prior, proposed)
    keep = [t for t in merged if t.text == "Send Carla the invoice"]
    assert len(keep) == 1 and keep[0].source == "human"


def test_unaddressed_prior_still_carries_forward():
    prior = [_todo("Old open action")]
    merged = merge_todos(prior, [_todo("New action")])
    assert {t.text for t in merged} == {"Old open action", "New action"}


def test_prioritize_skips_done_todos():
    from digest_core.state import Project

    p = Project(
        project_id="p1",
        client_id="c",
        title="t",
        open_todos=[_todo("live one"), _todo("closed one", done=True)],
    )
    ranked = prioritize([p], run_date="2026-06-08")
    texts = {r.todo.text for r in ranked}
    assert "live one" in texts and "closed one" not in texts


def test_observation_dismissed_round_trips():
    o = Observation.from_dict(
        {
            "date": "2026-06-08",
            "source": "model",
            "note": "X is dormant",
            "dismissed": True,
        }
    )
    assert o.dismissed is True and o.id == _content_id("X is dormant")


def test_freetext_due_hint_does_not_crash_ranking():
    # Regression: a model due_hint like "next 1-2 days" is not an ISO date; it must not crash the run.
    from digest_core.state import Project

    p = Project(
        project_id="p1",
        client_id="c",
        title="t",
        open_todos=[_todo("do it", due_hint="next 1-2 days")],
    )
    ranked = prioritize([p], run_date="2026-06-08")  # must not raise
    assert any(r.todo.text == "do it" for r in ranked)
