"""Tombstone-writing actions for the dashboard (docs/08). Every write here is a HUMAN-CONFIRMED change
to the single shared state model — a flag, not a hard delete — so the cron re-deriving from evidence
can't resurrect it. Never writes agent/observed fields."""

from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

from digest_core.state import (
    PROJECT_STATUSES,
    Observation,
    Project,
    Todo,
    write_projects,
)
from digest_web import service

router = APIRouter(prefix="/actions")


def _projects() -> list[Project]:
    return service.projects()


def _save(projects: list[Project]) -> None:
    write_projects(projects, service.state_dir() / "projects.json")


def _project(projects: list[Project], pid: str) -> Project | None:
    return next((p for p in projects if p.project_id == pid), None)


def _find_todo(p: Project, tid: str) -> Todo | None:
    for t in p.open_todos:
        if t.id == tid:
            return t
    for task in p.tasks:
        for t in task.open_todos:
            if t.id == tid:
                return t
    return None


@router.post("/todo/{pid}/{tid}/done", response_class=HTMLResponse)
def todo_done(pid: str, tid: str) -> HTMLResponse:
    projects = _projects()
    p = _project(projects, pid)
    t = _find_todo(p, tid) if p else None
    if t:
        t.done = True  # tombstone — stays closed across re-derivation
        _save(projects)
    return HTMLResponse('<div class="card muted">✓ done</div>')


@router.post("/project/{pid}/status", response_class=HTMLResponse)
def set_status(pid: str, status: str = Form(...)) -> HTMLResponse:
    if status not in PROJECT_STATUSES:
        return HTMLResponse(f"bad status {status!r}", status_code=400)
    projects = _projects()
    p = _project(projects, pid)
    if p:
        p.status_confirmed = status  # human-confirmed lifecycle (wins over the model)
        p.status = status  # reflect immediately in the dashboard view
        _save(projects)
    return HTMLResponse("", status_code=204)


@router.post("/project/{pid}/todo", response_class=HTMLResponse)
def add_todo(pid: str, text: str = Form(...)) -> HTMLResponse:
    text = text.strip()
    projects = _projects()
    p = _project(projects, pid)
    if p and text:
        p.open_todos.append(
            Todo(
                text=text,
                category="self",
                target=None,
                due_hint=None,
                rationale="added by Avigail",
                source_thread_id=None,
                source="human",  # protected from carry-forward clobbering
            )
        )
        _save(projects)
    return HTMLResponse("", status_code=204)


@router.post("/project/{pid}/note", response_class=HTMLResponse)
def add_note(pid: str, text: str = Form(...)) -> HTMLResponse:
    text = text.strip()
    projects = _projects()
    p = _project(projects, pid)
    if p and text:
        p.observations.append(
            Observation(date=service.today(), source="avigail", note=text)
        )
        _save(projects)
    return HTMLResponse("", status_code=204)


@router.post("/project/{pid}/note/{oid}/dismiss", response_class=HTMLResponse)
def dismiss_note(pid: str, oid: str) -> HTMLResponse:
    projects = _projects()
    p = _project(projects, pid)
    if p:
        for o in p.observations:
            if o.id == oid:
                o.dismissed = True  # tombstone — stays hidden, not re-added
        _save(projects)
    return HTMLResponse('<div class="card muted">✕ dismissed</div>')


@router.post("/project/{pid}/revive", response_class=HTMLResponse)
def revive(pid: str) -> HTMLResponse:
    projects = _projects()
    p = _project(projects, pid)
    if p:
        p.status_confirmed = "active"
        p.status = "active"
        _save(projects)
    return HTMLResponse("", status_code=204)
