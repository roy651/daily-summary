"""FastAPI app for Avigail's dashboard (docs/08). Read-only pages here; tombstone-writing actions are
mounted from actions.py. Run: `uv run uvicorn digest_web.app:app --host 0.0.0.0 --port 8080`."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

try:  # fastapi re-exports starlette's templating
    from fastapi.templating import Jinja2Templates
except Exception:  # pragma: no cover
    from starlette.templating import Jinja2Templates

from digest_web import actions, rerun, service

app = FastAPI(title="ula — Avigail's dashboard")
app.include_router(actions.router)
app.include_router(rerun.router)
_TPL = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _page(request: Request, name: str, **ctx) -> HTMLResponse:
    # Starlette's current signature is (request, name, context).
    ctx.setdefault(
        "last_run", service.last_run_at()
    )  # shown in the header on every page
    return _TPL.TemplateResponse(request, name, ctx)


@app.get("/", response_class=HTMLResponse)
def today(request: Request) -> HTMLResponse:
    run_date, digest_html = service.latest_digest()
    return _page(
        request, "today.html", tab="today", run_date=run_date, digest_html=digest_html
    )


@app.get("/todos", response_class=HTMLResponse)
def todos(request: Request) -> HTMLResponse:
    return _page(
        request,
        "todos.html",
        tab="todos",
        ranked=service.ranked_todos(),
        projects=service.active_projects(),
    )


@app.get("/projects", response_class=HTMLResponse)
def projects(request: Request) -> HTMLResponse:
    return _page(
        request,
        "projects.html",
        tab="projects",
        projects=service.active_projects(),
        archived=service.archived_projects(),
    )


@app.get("/projects/{pid}", response_class=HTMLResponse)
def project_detail(request: Request, pid: str) -> HTMLResponse:
    p = service.project(pid)
    if p is None:
        return HTMLResponse("<h1>404 — no such project</h1>", status_code=404)
    return _page(request, "project.html", tab="projects", p=p)


@app.get("/contacts", response_class=HTMLResponse)
def contacts(request: Request) -> HTMLResponse:
    store = service.contacts()
    by_role: dict[str, list] = {}
    for email, entry in store.items():
        if entry.alias_of:  # fold aliases under their canonical contact
            continue
        by_role.setdefault(entry.role, []).append((email, entry))
    return _page(request, "contacts.html", tab="contacts", by_role=by_role)


@app.get("/knowledge", response_class=HTMLResponse)
def knowledge(request: Request) -> HTMLResponse:
    notes = service.knowledge().general_notes()
    return _page(request, "knowledge.html", tab="knowledge", notes=notes)


@app.get("/clients", response_class=HTMLResponse)
def clients(request: Request) -> HTMLResponse:
    return _page(request, "clients.html", tab="clients", clients=service.clients())


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}
