"""Render the digest + the editable todo file (docs/02-pipeline.md).

Pure, deterministic formatting — no state mutation, no I/O. The digest is informational; the todo
file is the human-editable surface that FileDelivery reads back as feedback.
"""

from __future__ import annotations

import re

from digest_core.schema import ModelOutput
from digest_core.state import ClientProfile, Project
from digest_core.todos import BANDS, RankedTodo, prioritize

# Lifecycle statuses shown in the digest, in display order. Archived projects are hidden.
_STATUS_ORDER = ["blocked", "on_hold", "active", "done"]
_BAND_LABEL = {"urgent": "Urgent", "soon": "Soon", "whenever": "Whenever"}
_IMP_RANK = {"high": 0, "med": 1, "low": 2}

# Common words skipped when matching a project-less update to its closest project, so the overlap
# reflects distinctive terms (client/project names), not filler.
_STOPWORDS = frozenset(
    "the for and with from into new a an of to on re fwd update client project".split()
)


def _client_label(client_id: str, end_client: str | None) -> str:
    return f"{client_id} / {end_client}" if end_client else client_id


def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{3,}", s.lower()) if t not in _STOPWORDS}


def render_digest_md(
    output: ModelOutput,
    projects: list[Project],
    *,
    run_date: str,
    run_date_label: str | None = None,
    filtered: list | None = None,
    suspected: list | None = None,
) -> str:
    by_id = {p.project_id: p for p in projects}
    proj_tokens = {
        p.project_id: _tokens(f"{p.client_id} {p.end_client or ''} {p.title}")
        for p in projects
    }

    def _label_of(p: Project) -> str:
        return f"{_client_label(p.client_id, p.end_client)} — {p.title}"

    def _plabel(pid: str | None) -> str | None:
        """Client+project label for a project id ("sprig — RhythMedix logo"), or None if unknown."""
        p = by_id.get(pid) if pid else None
        return _label_of(p) if p else None

    def _closest_label(*text: str) -> str | None:
        """Best-effort client+project prefix for an update the model left project-less: match its text
        to the project with the most distinctive-token overlap (≥2). Avoids a bare 'General' bucket."""
        toks = _tokens(" ".join(text))
        best, score = None, 1  # require at least 2 shared tokens to claim a match
        for p in projects:
            s = len(toks & proj_tokens[p.project_id])
            if s > score:
                best, score = p, s
        return _label_of(best) if best else None

    ranked = prioritize(projects, run_date=run_date)
    # Todos suspected done/stale are pulled OUT of the active list (they fold into Updates below as
    # "likely done"), so the Todos section shows only genuinely-active work — not months of carry-forward.
    suspected_todo_keys = {
        (s.project_id, s.title)
        for s in (suspected or [])
        if s.kind in ("overdue_todo", "stale_todo")
    }
    ranked = [
        r for r in ranked if (r.project_id, r.todo.text) not in suspected_todo_keys
    ]
    lines: list[str] = [f"# Daily digest — {run_date_label or run_date}", ""]

    # ── 1. Email updates (Avigail's primary section) — grouped under client+project mini-headers ──
    lines.append("## 📬 Email updates")
    grouped: dict[str, list] = {}
    order: list[str] = []
    for u in sorted(
        output.digest_updates, key=lambda u: _IMP_RANK.get(u.importance, 1)
    ):
        key = _plabel(u.project_id) or _closest_label(u.headline, u.detail) or "General"
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(u)
    if not order:
        lines.append("_No notable updates._")
    for key in order:
        lines.append(f"#### {key}")
        for u in grouped[key]:
            detail = f" — {u.detail}" if u.detail else ""
            lines.append(f"- **{u.headline}**{detail}")
    # Fold the smaller "needs a glance" items into Updates instead of their own clutter of sections:
    # unplaced threads, entity/role confirmations, non-spam leads, and decay guesses. Personal stays below.
    # No thread ids here — they're raw Message-IDs (ugly noise for Avigail); the why text is enough.
    also: list[str] = []
    for u in output.unresolved:
        if u.kind == "personal":
            continue
        if u.kind == "lead":
            also.append(f"- 🌱 possible lead — {u.why}")
        elif u.kind == "entity":
            also.append(f"- 🤝 {u.why}")
        else:
            also.append(f"- 👀 {u.why}")
    for s in suspected or []:
        if s.kind == "dormant_project":
            also.append(f"- 💤 {s.title} — gone quiet; still active?  ({s.detail})")
        else:
            also.append(f"- ☑️ {s.title} — likely done  ({s.detail})")
    if also:
        lines.append("")
        lines.append("**Also worth a look**")
        lines.extend(also)
    lines.append("")

    # ── 2. Todos — by urgency band, each line led by the client+project it belongs to ──
    lines.append("## ✅ Todos")
    if not ranked:
        lines.append("_Nothing queued._")
    for band in BANDS:
        group = [r for r in ranked if r.band == band]
        if not group:
            continue
        lines.append(f"### {_BAND_LABEL[band]}")
        for r in group:
            label = _plabel(r.project_id) or _client_label(r.client_id, r.end_client)
            target = f" → {r.todo.target}" if r.todo.target else ""
            lines.append(f"- **{label}** · [{r.todo.category}] {r.todo.text}{target}")
    lines.append("")

    # ── 3. Project status (last) — only genuinely-active work; done/archived/dormant drop off ──
    dormant_ids = {
        s.project_id for s in (suspected or []) if s.kind == "dormant_project"
    }
    lines.append("## 🗂 Project status")
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
            f"- **{_client_label(p.client_id, p.end_client)} — {p.title}** — {p.status}{reason}{conf}"
        )
    lines.append("")

    # ── 4. Personal (bottom) — her non-business mail, surfaced but out of the way ──
    personal = [u for u in output.unresolved if u.kind == "personal"]
    if personal:
        lines.append("## 👤 Personal")
        for u in personal:
            # Strip a redundant leading "Personal:" the model sometimes adds — the section says it already.
            why = re.sub(r"^\s*personal\s*[:\-—]\s*", "", u.why, flags=re.IGNORECASE)
            lines.append(f"- {why}")
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
        "     forget = delete a wrong fact (paste a bit of its text) · alias = these emails are one person",
        "     note = tell me anything else -->",
        "# archive: ",
        "# revive: ",
        "# suppress: ",
        "# forget: ",
        "# alias: ",
        "# notes: ",
    ]


def render_state_review_md(
    clients: list[ClientProfile], projects: list[Project], contacts=None
) -> str:
    """A human-readable snapshot of what the system believes, for Avigail to eyeball + correct.

    Surfaces the accumulated client/project/contact map (with confidence + soft observations) so she
    can catch a misread (esp. a wrong contact role). Corrections via the feedback channel
    (`# alias:` / `# forget:` / notes) or by hand-editing state/*.json.
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
        managing = ", ".join(f"{m.name} <{m.email}>" for m in c.managing_contacts)
        lines.append(f"- **{c.display_name}** (`{c.client_id}`){agency}")
        if managing:
            lines.append(f"  - contacts: {managing}")
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

    # Contacts & roles — the entity map. Grouped by role so a mis-classified sub/agent/client is easy
    # to spot; fix with `# alias: a@x, b@y = subcontractor` or `# forget:` / a note in your feedback.
    items = contacts.items() if contacts is not None else []
    lines.append("## Contacts & roles")
    if not items:
        lines.append("_None._")
    else:
        # Fold aliased addresses under their canonical contact, so one person isn't shown as several.
        aliases_of: dict[str, list[str]] = {}
        for email, entry in items:
            if entry.alias_of:
                aliases_of.setdefault(entry.alias_of, []).append(email)
        by_role: dict[str, list[str]] = {}
        for email, entry in items:
            if entry.alias_of:
                continue  # listed under its canonical
            aka = aliases_of.get(email)
            aka_str = f" (aka {', '.join(aka)})" if aka else ""
            reason = _humanize_reason(entry.reason)
            line = f"- {email}{aka_str}" + (f" — _{reason}_" if reason else "")
            by_role.setdefault(entry.role, []).append(line)
        for role in sorted(by_role):
            lines.append(f"### {role}")
            lines.extend(by_role[role])
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# Plain-English provenance for the audit surface (the stored `reason` strings are terse/internal).
_REASON_HUMAN = {
    "communicate_client target": "someone you communicate with on a project",
    "verify_subcontractor target": "a subcontractor whose work you verify",
    "project subcontractor": "subcontractor on a project",
    "task subcontractor": "subcontractor on a task",
    "invoices ULA": "invoices you (billing signal)",
    "invoiced by ULA": "you invoice them (billing signal)",
    "merged: same person/entity": "merged — same person",
}


def _humanize_reason(reason: str) -> str:
    return _REASON_HUMAN.get(reason, reason)
