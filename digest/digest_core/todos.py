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
    if days_to_due is not None:
        weight = 1.0 if deadline_kind == "hard" else 0.4
        score += max(0.0, 30 - days_to_due) * weight
        if deadline_kind == "hard" and days_to_due <= 2:
            hard_soon = True

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
