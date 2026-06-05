"""TODO carry-forward + prioritization (docs/03-todo-model.md).

The model proposes todos; this module ranks them deterministically (testable, stable run-to-run)
and carries forward prior todos the model didn't address ("surface, don't drop"). Prioritization is
filled in alongside its task; ``merge_todos`` is needed first because apply.py depends on it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from digest_core.state import Project, Todo

# Bands, in descending urgency. Rendering groups by band -> category -> client.
BANDS = ("urgent", "soon", "whenever")
_BLOCKED_STATUSES = frozenset({"blocked", "on_hold"})
_UNBLOCKING_CATEGORIES = frozenset({"communicate_client", "verify_subcontractor"})


def _norm_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def merge_todos(prior: list[Todo], proposed: list[Todo]) -> list[Todo]:
    """Proposed todos win; prior todos the model didn't restate are carried forward, not deleted.

    Match is by normalized text. A prior todo whose text matches a proposed one is considered
    addressed (the proposed version replaces it). Anything else from `prior` is retained so an
    unaddressed action never silently vanishes between runs.
    """
    proposed_keys = {_norm_text(t.text) for t in proposed}
    carried = [t for t in prior if _norm_text(t.text) not in proposed_keys]
    return list(proposed) + carried


# ── prioritization ──────────────────────────────────────────────────────────────


@dataclass
class RankedTodo:
    todo: Todo
    project_id: str
    client_id: str
    end_client: str | None
    task_id: str | None  # which task it hangs off (None = project-level)
    score: float
    band: str


def _days_between(start_iso: str | None, end_iso: str | None) -> int | None:
    if not start_iso or not end_iso:
        return None
    return (date.fromisoformat(end_iso) - date.fromisoformat(start_iso)).days


def _score(
    todo: Todo,
    project: Project,
    *,
    deadline: str | None,
    deadline_kind: str | None,
    run_date: str,
):
    """Composite urgency from deadline pressure + blocker leverage + staleness. Returns (score, hard_soon)."""
    score = 0.0
    hard_soon = False

    # 1. Deadline pressure — closer hard deadline => higher; soft deadlines contribute less.
    days_to_due = _days_between(run_date, deadline)
    if days_to_due is not None and days_to_due >= 0:
        weight = 1.0 if deadline_kind == "hard" else 0.4
        score += max(0.0, 30 - days_to_due) * weight
        if deadline_kind == "hard" and days_to_due <= 2:
            hard_soon = True
    elif days_to_due is not None and days_to_due < 0:
        # Overdue: a modest nudge (it's genuinely past due → address it), never the runaway max-urgency
        # of the old bug (D1). If the project is ALSO stale, decay routes it to "suspected done" instead.
        score += 6.0

    # 2. Blocker leverage — an action that unblocks a stalled project is high-leverage.
    if project.status in _BLOCKED_STATUSES and todo.category in _UNBLOCKING_CATEGORIES:
        score += 15.0

    # 3. Staleness — silence escalates so nothing falls through.
    stale_days = _days_between(project.last_activity_date, run_date)
    if stale_days and stale_days > 0:
        score += min(stale_days, 30) * 0.5

    return score, hard_soon


def _band(score: float, hard_soon: bool) -> str:
    if hard_soon or score >= 20:
        return "urgent"
    if score >= 8:
        return "soon"
    return "whenever"


def prioritize(projects: list[Project], *, run_date: str) -> list[RankedTodo]:
    """Rank every open todo (project- and task-level) into urgency bands. Deterministic ordering."""
    ranked: list[RankedTodo] = []
    for p in projects:
        # Project-level todos use the project's own deadline.
        for todo in p.open_todos:
            deadline = todo.due_hint or p.deadline
            score, hard_soon = _score(
                todo,
                p,
                deadline=deadline,
                deadline_kind=p.deadline_kind,
                run_date=run_date,
            )
            ranked.append(
                RankedTodo(
                    todo,
                    p.project_id,
                    p.client_id,
                    p.end_client,
                    None,
                    score,
                    _band(score, hard_soon),
                )
            )
        # Task-level todos prefer the task deadline, falling back to the project's. A due_hint is the
        # model's *soft* guess, so it uses the project's deadline_kind — never silently "hard" (F4).
        for task in p.tasks:
            for todo in task.open_todos:
                deadline = todo.due_hint or task.deadline or p.deadline
                score, hard_soon = _score(
                    todo,
                    p,
                    deadline=deadline,
                    deadline_kind=p.deadline_kind,
                    run_date=run_date,
                )
                ranked.append(
                    RankedTodo(
                        todo,
                        p.project_id,
                        p.client_id,
                        p.end_client,
                        task.task_id,
                        score,
                        _band(score, hard_soon),
                    )
                )

    # Sort by score desc, then project_id asc, then todo text asc — fully deterministic.
    ranked.sort(key=lambda r: (-r.score, r.project_id, r.todo.text))
    return ranked


# ── decay / closure (the "remove" half) ──────────────────────────────────────────


@dataclass
class Suspicion:
    """A surfaced guess that something can be cleared — never auto-deleted, always confirmed."""

    kind: str  # "dormant_project" | "overdue_todo" | "stale_todo"
    project_id: str
    title: str  # project title (dormant) or todo text (todo)
    detail: (
        str  # why we suspect it (e.g. "silent 41 days", "deadline 2026-04-01 passed")
    )


def _days(a: str | None, b: str | None) -> int | None:
    return _days_between(a, b)


def suspected_closures(
    projects: list[Project],
    *,
    run_date: str,
    dormant_after_days: int = 28,
    stale_todo_after_days: int = 21,
    overdue_needs_silent_days: int = 14,
) -> list[Suspicion]:
    """Decay pass: surface (do NOT delete) projects/todos that look finished or dormant.

      * dormant_project: an active/blocked project with no activity for `dormant_after_days`.
      * overdue_todo: a todo whose (hard or soft) deadline has passed — most likely already done.
      * stale_todo: a todo on a project that's seen newer activity than the todo, for long enough that
        the model never restating it suggests it's done.
    These feed the digest's "Suspected done / dormant — confirm to clear" section.
    """
    out: list[Suspicion] = []
    for p in projects:
        if p.status in ("done", "archived"):
            continue
        silent = _days(p.last_activity_date, run_date)
        if silent is not None and silent >= dormant_after_days:
            out.append(
                Suspicion(
                    "dormant_project", p.project_id, p.title, f"silent {silent} days"
                )
            )

        all_todos = [(None, t) for t in p.open_todos] + [
            (tk.task_id, t) for tk in p.tasks for t in tk.open_todos
        ]
        for _task_id, todo in all_todos:
            due = todo.due_hint or p.deadline
            dd = _days(run_date, due)
            # Overdue ⇒ "probably done" ONLY if the project is ALSO stale; on a fresh/active project an
            # overdue todo is genuinely due-now (stays in the list, nudged), not a completion to confirm.
            if (
                dd is not None
                and dd < 0
                and silent is not None
                and silent >= overdue_needs_silent_days
            ):
                out.append(
                    Suspicion(
                        "overdue_todo",
                        p.project_id,
                        todo.text,
                        f"deadline {due} passed, project silent {silent}d",
                    )
                )
            elif not (dd is not None and dd < 0):
                stale = _days(p.last_activity_date, run_date)
                if stale is not None and stale >= stale_todo_after_days:
                    out.append(
                        Suspicion(
                            "stale_todo",
                            p.project_id,
                            todo.text,
                            f"untouched {stale} days",
                        )
                    )
    return out


def _rendered_todo_key(todo: Todo, client_id: str, end_client: str | None) -> str:
    """Reconstruct the body of a rendered todo line (sans checkbox + marker), normalized — the exact
    key a checked-off line round-trips to. Mirrors render.render_todos_md's line body. EXACT match (not
    substring) so checking 'Send the brochure to Acme' never silently closes a sibling 'Send the brochure'."""
    target = f" → {todo.target}" if todo.target else ""
    client = f"{client_id} / {end_client}" if end_client else client_id
    return _norm_text(f"[{todo.category}] {todo.text}{target}  ({client})")


def close_todos_from_feedback(projects: list[Project], done_items: list[str]) -> int:
    """Remove open todos Avigail checked off, matching each checked line to a todo by EXACT normalized
    rendered-line equality (G2). Returns the count closed. Highest-confidence closure: her explicit done-mark."""
    done = {_norm_text(d) for d in done_items}
    closed = 0

    def _filter(
        todos: list[Todo], client_id: str, end_client: str | None
    ) -> list[Todo]:
        nonlocal closed
        kept = []
        for t in todos:
            if _rendered_todo_key(t, client_id, end_client) in done:
                closed += 1
            else:
                kept.append(t)
        return kept

    for p in projects:
        p.open_todos = _filter(p.open_todos, p.client_id, p.end_client)
        for task in p.tasks:
            task.open_todos = _filter(task.open_todos, p.client_id, p.end_client)
    return closed


def auto_archive_billed(
    projects: list[Project], *, run_date: str, silent_days: int = 7
) -> list[str]:
    """Evidence-based, REVERSIBLE project closure: a fully-billed project (``billed_on`` set) with no
    new activity for ``silent_days`` is archived automatically. Skips human-confirmed-active projects.
    Revival is handled in apply (a new item flips it back to active and clears ``billed_on``).
    Returns the archived project ids."""
    archived: list[str] = []
    for p in projects:
        if p.status == "active" and p.billed_on and not p.status_confirmed:
            silent = _days(p.last_activity_date, run_date)
            if silent is not None and silent >= silent_days:
                p.status = "archived"
                archived.append(p.project_id)
    return archived
