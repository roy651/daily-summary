"""Render the digest + the editable todo file (docs/02-pipeline.md).

Pure, deterministic formatting — no state mutation, no I/O. The digest is informational; the todo
file is the human-editable surface that FileDelivery reads back as feedback.
"""

from __future__ import annotations

from digest_core.schema import ModelOutput
from digest_core.state import ClientProfile, Project
from digest_core.todos import BANDS, RankedTodo, prioritize

# Lifecycle statuses shown in the digest, in display order. Archived projects are hidden.
_STATUS_ORDER = ["blocked", "on_hold", "active", "done"]
_BAND_LABEL = {"urgent": "Urgent", "soon": "Soon", "whenever": "Whenever"}
_IMPORTANCE_LABEL = {"high": "High", "med": "Medium", "low": "Low"}


def _client_label(client_id: str, end_client: str | None) -> str:
    return f"{client_id} / {end_client}" if end_client else client_id


def _ranked_line(r: RankedTodo) -> str:
    target = f" → {r.todo.target}" if r.todo.target else ""
    return f"- [{r.todo.category}] {r.todo.text}{target}  ({_client_label(r.client_id, r.end_client)})"


def render_digest_md(
    output: ModelOutput,
    projects: list[Project],
    *,
    run_date: str,
    run_date_label: str | None = None,
    filtered: list | None = None,
    suspected: list | None = None,
) -> str:
    ranked = prioritize(projects, run_date=run_date)
    # Todos suspected done/stale move OUT of the active list into "confirm to clear" — so the main
    # TODO list shows only genuinely-active work, not months of likely-completed carry-forward.
    suspected_todo_keys = {
        (s.project_id, s.title)
        for s in (suspected or [])
        if s.kind in ("overdue_todo", "stale_todo")
    }
    ranked = [
        r for r in ranked if (r.project_id, r.todo.text) not in suspected_todo_keys
    ]
    lines: list[str] = [f"# Daily digest — {run_date_label or run_date}", ""]

    # 1. Project status — only genuinely-active work. Done/archived drop off; suspected-dormant move to
    # the "confirm to clear" section below (so the status list isn't padded with quiet/finished work).
    dormant_ids = {
        s.project_id for s in (suspected or []) if s.kind == "dormant_project"
    }
    lines.append("## Project status")
    visible = [
        p
        for p in projects
        if p.status not in ("archived", "done") and p.project_id not in dormant_ids
    ]
    visible.sort(
        key=lambda p: (
            _STATUS_ORDER.index(p.status) if p.status in _STATUS_ORDER else 99,
            p.project_id,
        )
    )
    if not visible:
        lines.append("_No active projects._")
    for p in visible:
        reason = f": {p.status_reason}" if p.status_reason else ""
        conf = f" _(confidence: {p.confidence})_" if p.confidence else ""
        lines.append(
            f"- **{p.title}** ({_client_label(p.client_id, p.end_client)}) — {p.status}{reason}{conf}"
        )
    lines.append("")

    # 2. Important updates (last ~24h)
    lines.append("## Important updates (last 24h)")
    if not output.digest_updates:
        lines.append("_No notable updates._")
    for importance in ("high", "med", "low"):
        group = [u for u in output.digest_updates if u.importance == importance]
        if not group:
            continue
        lines.append(f"### {_IMPORTANCE_LABEL[importance]}")
        for u in group:
            detail = f" — {u.detail}" if u.detail else ""
            lines.append(f"- **{u.headline}**{detail}")
    lines.append("")

    # 3. Prioritized TODO list
    lines.append("## TODO — next day or two")
    if not ranked:
        lines.append("_Nothing queued._")
    for band in BANDS:
        group = [r for r in ranked if r.band == band]
        if not group:
            continue
        lines.append(f"### {_BAND_LABEL[band]}")
        lines.extend(_ranked_line(r) for r in group)
    lines.append("")

    # 4. Unresolved threads, surfaced (never dropped) and split by kind so personal mail and entity
    #    questions don't hide among unplaced business threads. 'unplaced' is the catch-all.
    for kind, title in (
        ("personal", "Personal"),
        ("lead", "Possible new leads"),
        ("entity", "New people / roles — confirm"),
        ("unplaced", "Needs your eye"),
    ):
        group = [
            u
            for u in output.unresolved
            if u.kind == kind
            or (kind == "unplaced" and u.kind not in ("personal", "lead", "entity"))
        ]
        if not group:
            continue
        lines.append(f"## {title}")
        for u in group:
            lines.append(f"- thread `{u.thread_id}`: {u.why}")
        lines.append("")

    # 5. Suspected done / dormant — decay guesses surfaced for confirmation; NEVER auto-cleared.
    if suspected:
        lines.append("## Suspected done / dormant — confirm to clear")
        dormant = [s for s in suspected if s.kind == "dormant_project"]
        todos_s = [s for s in suspected if s.kind != "dormant_project"]
        if dormant:
            lines.append("_Projects gone quiet — still active?_")
            for s in dormant:
                lines.append(f"- **{s.title}** (`{s.project_id}`) — {s.detail}")
        if todos_s:
            lines.append("_TODOs likely already done — clear them?_")
            for s in todos_s[:12]:
                lines.append(f"- {s.title}  _({s.detail})_")
            if len(todos_s) > 12:
                lines.append(f"- _(+{len(todos_s) - 12} more)_")
        lines.append("")

    # 6. Filtered as bulk/marketing — surfaced (capped) so a misfire is visible, not silently dropped.
    if filtered:
        lines.append(
            f"## Filtered as bulk/marketing ({len(filtered)}) — flag any that matter"
        )
        for t in filtered[:8]:
            subj = (
                (t.records[0].subject or "(no subject)").strip()
                if t.records
                else "(empty)"
            )
            sender = (t.records[0].from_ or "?") if t.records else "?"
            lines.append(f"- {subj}  — _{sender}_")
        if len(filtered) > 8:
            lines.append(f"- _(+{len(filtered) - 8} more)_")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_todos_md(ranked: list[RankedTodo], *, run_date: str) -> str:
    """The editable todo surface. Each line carries a project marker for feedback round-trip."""
    lines = [
        f"# TODOs — {run_date}",
        "# Edit freely (check off, reorder, delete, add). Saved changes are read back as feedback.",
        "",
    ]
    for band in BANDS:
        group = [r for r in ranked if r.band == band]
        if not group:
            continue
        lines.append(f"## {_BAND_LABEL[band]}")
        for r in group:
            target = f" → {r.todo.target}" if r.todo.target else ""
            marker = (
                r.project_id if r.task_id is None else f"{r.project_id}/{r.task_id}"
            )
            lines.append(
                f"- [ ] [{r.todo.category}] {r.todo.text}{target}  "
                f"({_client_label(r.client_id, r.end_client)}) <!-- {marker} -->"
            )
        lines.append("")
    lines.extend(_feedback_template())
    return "\n".join(lines).rstrip() + "\n"


def _feedback_template() -> list[str]:
    """A fill-in-the-blanks feedback block appended to the todo file. The directive lines are live but
    empty (no-ops until filled); the whole file is regenerated next run, so filled feedback 'clears'
    after it's read. parse_todos_md ignores the heading/comment and treats empty directives as no-ops."""
    return [
        "## ✎ Feedback (optional) — fill any line, save; it's applied next run, then resets",
        "<!-- check off done items above with [x]. Then, after each tag below, add ids/text:",
        "     archive = a finished/dormant project · revive = bring one back · suppress = hide a thread",
        "     note = tell me anything, incl. fixing who someone is (e.g. an entity/role correction) -->",
        "# archive: ",
        "# revive: ",
        "# suppress: ",
        "# notes: ",
    ]


def render_state_review_md(
    clients: list[ClientProfile], projects: list[Project]
) -> str:
    """A human-readable snapshot of what the system believes, for Avigail to eyeball + correct.

    Surfaces the accumulated client/project map (with confidence + soft observations) so she can
    catch a misread. Corrections are made by hand-editing state/*.json (v1) or via feedback (phase 2).
    """
    lines: list[str] = ["# State review — what the system currently believes", ""]
    lines.append(
        "_Eyeball this and correct anything wrong: edit state/clients.json or state/projects.json "
        "directly (round-trip-safe), or note it in your feedback._"
    )
    lines.append("")

    active = [c for c in clients if c.status != "archived"]
    lines.append("## Clients")
    if not active:
        lines.append("_None._")
    for c in sorted(active, key=lambda c: c.client_id):
        agency = " — agency" if c.is_agency else ""
        contacts = ", ".join(f"{m.name} <{m.email}>" for m in c.managing_contacts)
        lines.append(f"- **{c.display_name}** (`{c.client_id}`){agency}")
        if contacts:
            lines.append(f"  - contacts: {contacts}")
        for o in c.observations:
            lines.append(f"  - _{o.date}_: {o.note}")
    lines.append("")

    visible = [p for p in projects if p.status != "archived"]
    lines.append("## Projects")
    if not visible:
        lines.append("_None._")
    for p in sorted(visible, key=lambda p: (p.client_id, p.project_id)):
        conf = f", confidence {p.confidence}" if p.confidence else ""
        deadline = f", deadline {p.deadline} ({p.deadline_kind})" if p.deadline else ""
        lines.append(
            f"- **{p.title}** (`{p.project_id}`, {_client_label(p.client_id, p.end_client)}) "
            f"— {p.status}{conf}{deadline}"
        )
        if p.status_reason:
            lines.append(f"  - {p.status_reason}")
        for o in p.observations:
            lines.append(f"  - _{o.date}_: {o.note}")
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"
