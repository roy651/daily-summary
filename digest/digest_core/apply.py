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


def _title_tokens(title: str) -> set[str]:
    return {tok for tok in re.findall(r"[a-z0-9]+", title.lower()) if len(tok) > 2}


def _find_match(projects: list[Project], update: ProjectUpdate) -> Project | None:
    if update.project_id is not None:
        for p in projects:
            if p.project_id == update.project_id:
                return p
    # Fall back to (client_id, normalized-title) overlap so a fresh model id doesn't duplicate.
    if update.client_id and update.title:
        want = _title_tokens(update.title)
        for p in projects:
            if p.client_id != update.client_id:
                continue
            have = _title_tokens(p.title)
            if not want or not have:
                continue
            overlap = len(want & have) / min(len(want), len(have))
            if overlap >= 0.6:
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
    if update.blockers:
        project.blockers = update.blockers
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
    for update in output.project_updates:
        match = _find_match(result, update)
        if match is None:
            result.append(_new_project(update, run_date, thread_dates))
        else:
            _apply_one(match, update, run_date, thread_dates)
    return result
