"""Dashboard (docs/08): read-only pages render from the shared state, and every action writes a
HUMAN-CONFIRMED tombstone without touching agent/observed fields (the invariant, as a test)."""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")  # fastapi TestClient needs httpx

from fastapi.testclient import TestClient  # noqa: E402

from digest_core.state import (  # noqa: E402
    Observation,
    Project,
    Todo,
    load_projects,
    write_projects,
)


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    state = tmp_path / "state"
    out = tmp_path / "out"
    state.mkdir()
    out.mkdir()
    todo = Todo(
        text="do the thing",
        category="self",
        target=None,
        due_hint=None,
        rationale="",
        source_thread_id=None,
    )
    obs = Observation(date="2026-06-08", source="model", note="gone quiet?")
    p = Project(
        project_id="p1",
        client_id="sprig",
        title="Logo",
        status_agent="active",
        open_todos=[todo],
        observations=[obs],
    )
    write_projects([p], state / "projects.json")
    (out / "digest_2026-06-08.md").write_text(
        "# Daily digest\n## 📬 Email updates\n- hi\n", encoding="utf-8"
    )
    monkeypatch.setenv("STATE_DIR", str(state))
    monkeypatch.setenv("OUT_DIR", str(out))
    from digest_web.app import app

    return TestClient(app), state, todo.id, obs.id


def test_read_only_pages_render(ctx):
    client = ctx[0]
    assert client.get("/").status_code == 200
    assert "do the thing" in client.get("/todos").text
    assert "Logo" in client.get("/projects").text
    assert client.get("/projects/p1").status_code == 200
    for tab in ("/contacts", "/knowledge", "/clients"):
        assert client.get(tab).status_code == 200


def test_close_todo_writes_done_tombstone_not_agent_fields(ctx):
    client, state, tid, _ = ctx
    assert client.post(f"/actions/todo/p1/{tid}/done").status_code == 200
    p = load_projects(state / "projects.json")[0]
    assert p.open_todos[0].done is True
    assert p.status_agent == "active"  # agent field untouched (the invariant)


def test_status_change_writes_human_confirmed(ctx):
    client, state, _, _ = ctx
    client.post("/actions/project/p1/status", data={"status": "on_hold"})
    p = load_projects(state / "projects.json")[0]
    assert p.status_confirmed == "on_hold" and p.status == "on_hold"


def test_dismiss_note_and_add_human_todo_and_note(ctx):
    client, state, _, oid = ctx
    client.post(f"/actions/project/p1/note/{oid}/dismiss")
    client.post("/actions/project/p1/todo", data={"text": "call Carla"})
    client.post("/actions/project/p1/note", data={"text": "client prefers blue"})
    p = load_projects(state / "projects.json")[0]
    assert any(o.dismissed for o in p.observations)
    assert any(t.text == "call Carla" and t.source == "human" for t in p.open_todos)
    assert any(
        o.note == "client prefers blue" and o.source == "avigail"
        for o in p.observations
    )
