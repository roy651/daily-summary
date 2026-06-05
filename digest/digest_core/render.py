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
) -> str:
    ranked = prioritize(projects, run_date=run_date)
    lines: list[str] = [f"# Daily digest — {run_date_label or run_date}", ""]

    # 1. Project status
    lines.append("## Project status")
    visible = [p for p in projects if p.status != "archived"]
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

    # 4. Needs your eye — low-confidence / unplaced threads (surface, don't drop)
    if output.unresolved:
        lines.append("## Needs your eye")
        for u in output.unresolved:
            lines.append(f"- thread `{u.thread_id}`: {u.why}")
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
    return "\n".join(lines).rstrip() + "\n"


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
