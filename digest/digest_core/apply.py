"""apply_model_output — deterministic, guarded merge of MODEL PASS output into state (docs/05).

Invariants enforced here:
  * writes ONLY observed + agent-proposed columns — NEVER a human-confirmed column;
  * the effective lifecycle `status` prefers Avigail's `status_confirmed` override when present,
    else the agent's read (apply *reads* confirmed but never *writes* it);
  * `last_activity_date` is recomputed from evidence dates, never taken from the model;
  * a model update matches an existing project by id, else by (client_id, normalized title) so a
    model-coined id can't duplicate a known project;
  * todos are carry-forward-merged so an unaddressed prior action is never silently dropped.
"""

from __future__ import annotations

import re

from digest_core.schema import ModelOutput, ProjectUpdate
from digest_core.state import Project
from digest_core.todos import merge_todos


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-") or "project"


def _norm_title(title: str) -> str:
    """Normalized title key: lowercased, alphanumeric tokens, sorted — so word-order/spacing differences
    still match but distinct titles don't (avoids the F5 subset-merge: 'logo' vs 'logo refresh')."""
    return " ".join(sorted(re.findall(r"[a-z0-9]+", title.lower())))


def _find_match(projects: list[Project], update: ProjectUpdate) -> Project | None:
    # 1. Direct id match (the model echoed a known project_id).
    if update.project_id is not None:
        for p in projects:
            if p.project_id == update.project_id:
                return p
    # 2. Shared evidence thread — strongest signal that this is the same project.
    if update.evidence_thread_ids:
        want_threads = set(update.evidence_thread_ids)
        for p in projects:
            if want_threads & set(p.evidence_thread_ids):
                return p
    # 3. Same client + EXACT normalized title. We deliberately do NOT fuzzy-match (F5): a wrong
    #    merge clobbers a real project; on ambiguity we prefer a duplicate the human can merge.
    if update.client_id and update.title:
        want = _norm_title(update.title)
        for p in projects:
            if p.client_id == update.client_id and _norm_title(p.title) == want:
                return p
    return None


def _max_evidence_date(
    thread_ids: list[str], thread_dates: dict[str, str]
) -> str | None:
    dates = [thread_dates[tid] for tid in thread_ids if tid in thread_dates]
    return max(dates) if dates else None


def _apply_one(
    project: Project, update: ProjectUpdate, run_date: str, thread_dates: dict[str, str]
) -> None:
    # Agent-proposed columns (rewritten each run).
    if update.status_agent is not None:
        project.status_agent = update.status_agent
    project.status_evidence = update.status_evidence
    if update.confidence is not None:
        project.confidence = update.confidence
    if update.evidence_thread_ids:
        merged = list(
            dict.fromkeys([*project.evidence_thread_ids, *update.evidence_thread_ids])
        )
        project.evidence_thread_ids = merged
    # None = field omitted (keep existing); [] = the model explicitly cleared the blockers (F6).
    if update.blockers is not None:
        project.blockers = update.blockers
    # Auto-expire blockers whose blocks_until has passed, so stale blockers don't inflate priority.
    project.blockers = [
        b
        for b in project.blockers
        if not (b.blocks_until and b.blocks_until < run_date)
    ]
    if update.deadline is not None:
        project.deadline = update.deadline
    if update.deadline_kind is not None:
        project.deadline_kind = update.deadline_kind
    if update.end_client is not None:
        project.end_client = update.end_client
    if update.assignee is not None:
        project.assignee = update.assignee
    if update.subcontractor is not None:
        project.subcontractor = update.subcontractor

    # Effective lifecycle status: human override wins; else the agent's read.
    project.status = project.status_confirmed or project.status_agent or project.status

    # Carry-forward-merge todos (surface, don't drop).
    project.open_todos = merge_todos(project.open_todos, update.todos)

    # Observed-truth: advance last_activity_date from evidence only, never regress.
    ev_date = _max_evidence_date(project.evidence_thread_ids, thread_dates)
    if ev_date and (
        project.last_activity_date is None or ev_date > project.last_activity_date
    ):
        project.last_activity_date = ev_date

    project.last_seen_run = run_date


def _new_project(
    update: ProjectUpdate, run_date: str, thread_dates: dict[str, str]
) -> Project:
    pid = update.project_id or f"{update.client_id}-{_slug(update.title or '')}"
    project = Project(
        project_id=pid,
        client_id=update.client_id or "",
        title=update.title or "",
        end_client=update.end_client,
        assignee=update.assignee or "self",
        subcontractor=update.subcontractor,
        status=update.status_agent or "active",
    )
    _apply_one(project, update, run_date, thread_dates)
    return project


def apply_model_output(
    projects: list[Project],
    output: ModelOutput,
    *,
    run_date: str,
    thread_dates: dict[str, str] | None = None,
) -> list[Project]:
    """Apply the model's project updates onto `projects` (mutating in place, appending new ones)."""
    thread_dates = thread_dates or {}
    result = list(projects)
    # Snapshot the human-confirmed columns; apply must never write them (runtime guard for F10).
    confirmed_before = {id(p): (p.status_confirmed, p.confirmed_note) for p in result}
    for update in output.project_updates:
        match = _find_match(result, update)
        if match is None:
            result.append(_new_project(update, run_date, thread_dates))
        else:
            _apply_one(match, update, run_date, thread_dates)
    for p in result:
        if id(p) in confirmed_before:
            assert (p.status_confirmed, p.confirmed_note) == confirmed_before[id(p)], (
                f"apply must never write human-confirmed columns (project {p.project_id})"
            )
    return result
