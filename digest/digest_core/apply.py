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

from digest_core.knowledge import KnowledgeStore
from digest_core.schema import ModelOutput, ProjectUpdate
from digest_core.state import ClientProfile, Observation, Project
from digest_core.todos import _norm_text, merge_todos


def _append_observations(target, notes: list[str], run_date: str) -> None:
    """Append free-text notes as Observations, de-duplicated by note text (knowledge accretes)."""
    have = {o.note.strip().lower() for o in target.observations}
    for note in notes:
        if note.strip() and note.strip().lower() not in have:
            target.observations.append(
                Observation(date=run_date, source="agent", note=note.strip())
            )
            have.add(note.strip().lower())


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
    prev_status = project.status
    # Agent-proposed columns (rewritten each run).
    if update.status_agent is not None:
        project.status_agent = update.status_agent
    if update.billed:
        project.billed_on = (
            run_date  # fully invoiced -> eligible for billed+silence auto-archive
        )
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
    # Revival (reversible closure): a done/archived project that's active again got a NEW item — start a
    # fresh billing cycle so it isn't immediately re-archived by the billed+silence rule.
    if prev_status in ("done", "archived") and project.status not in (
        "done",
        "archived",
    ):
        project.billed_on = None

    # Carry-forward-merge todos (surface, don't drop)...
    project.open_todos = merge_todos(project.open_todos, update.todos)
    # ...then CLOSE the ones the model judged completed (evidence-based removal — the close half of add).
    if update.closed_todos:
        closed = {_norm_text(t) for t in update.closed_todos}
        project.open_todos = [
            t for t in project.open_todos if _norm_text(t.text) not in closed
        ]
        for task in project.tasks:
            task.open_todos = [
                t for t in task.open_todos if _norm_text(t.text) not in closed
            ]

    # Accumulate tacit project knowledge.
    _append_observations(project, update.observations, run_date)

    # Observed-truth: advance last_activity_date from evidence, never regress. When precise evidence
    # dates aren't available, a project the model TOUCHED this run still had activity — floor it at the
    # run date so the decay/dormancy clock is meaningful (untouched projects keep their old date and age).
    ev_date = _max_evidence_date(project.evidence_thread_ids, thread_dates)
    if ev_date and (
        project.last_activity_date is None or ev_date > project.last_activity_date
    ):
        project.last_activity_date = ev_date
    elif project.last_activity_date is None or project.last_activity_date < run_date:
        project.last_activity_date = run_date

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
    # R1: an explicit raise (not assert) so this non-negotiable invariant survives `python -O`.
    for p in result:
        if (
            id(p) in confirmed_before
            and (p.status_confirmed, p.confirmed_note) != confirmed_before[id(p)]
        ):
            raise RuntimeError(
                f"apply must never write human-confirmed columns (project {p.project_id})"
            )
    return result


def apply_insights(
    output: ModelOutput,
    clients: list[ClientProfile],
    knowledge: KnowledgeStore,
    *,
    run_date: str,
) -> None:
    """Route the model's tacit-knowledge insights: scope 'general' -> knowledge store; a client_id ->
    that client's observations. Unknown client scopes fall back to the general store (never dropped)."""
    by_id = {c.client_id: c for c in clients}
    for ins in output.insights:
        if ins.scope == "general" or ins.scope not in by_id:
            knowledge.add_general(ins.note, date=run_date)
        else:
            _append_observations(by_id[ins.scope], [ins.note], run_date)


def upsert_clients(
    projects: list[Project], existing: list[ClientProfile] | None = None
) -> list[ClientProfile]:
    """Ensure every project's client_id has a ClientProfile (K3). Existing profiles are preserved
    untouched (incl. human edits like is_agency); only missing clients get a stub. Used by both
    bootstrap (cold start from []) and daily (new clients discovered after bootstrap)."""
    known = {c.client_id: c for c in (existing or [])}
    for p in projects:
        if p.client_id and p.client_id not in known:
            known[p.client_id] = ClientProfile(
                client_id=p.client_id,
                display_name=p.client_id.replace("-", " ").replace("_", " ").title(),
            )
    return [known[k] for k in sorted(known)]


_EMAIL_RE = re.compile(r"[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+")


def _looks_like_email(value: str | None) -> bool:
    return bool(value and _EMAIL_RE.fullmatch(value.strip()))


def promote_work_contacts(
    projects: list[Project], clients: list[ClientProfile], contacts, *, run_date: str
) -> None:
    """Add to the contact store the people the model tied to real work (the reasoning test: 'was there
    genuine work correspondence?'). Derived from the MERGED project state. Roles:
      * a project's subcontractor                       -> subcontractor
      * a verify_subcontractor todo target              -> subcontractor
      * a communicate_client todo target on AGENCY work -> agent (reached via the agent)
      * a communicate_client todo target on DIRECT work -> client
    "Agency work" = the project's client is an agency (e.g. SPRIG) — whether for one of the agency's
    end-clients (``end_client`` set) OR for the agency itself (``end_client`` None, e.g. SPRIG-direct
    work). Keying off the client's ``is_agency`` (not merely ``end_client``) correctly tags an agency
    manager like Katie on SPRIG-direct work as an *agent*, not a client.
    This replaces indiscriminate bootstrap seeding, so only work-relevant contacts become known/T1."""
    agency_clients = {c.client_id for c in clients if c.is_agency}

    def _promote(p: Project, todos) -> None:
        is_agency_work = p.client_id in agency_clients or bool(p.end_client)
        for todo in todos:
            if not _looks_like_email(todo.target):
                continue
            if todo.category == "verify_subcontractor":
                role = "subcontractor"
            elif todo.category == "communicate_client":
                role = "agent" if is_agency_work else "client"
            else:
                continue
            contacts.add(
                todo.target,
                role=role,
                source="model",
                reason=f"{todo.category} target",
                added=run_date,
            )

    for p in projects:
        if _looks_like_email(p.subcontractor):
            contacts.add(
                p.subcontractor,
                role="subcontractor",
                source="model",
                reason="project subcontractor",
                added=run_date,
            )
        _promote(p, p.open_todos)
        for task in p.tasks:
            if _looks_like_email(task.subcontractor):
                contacts.add(
                    task.subcontractor,
                    role="subcontractor",
                    source="model",
                    reason="task subcontractor",
                    added=run_date,
                )
            _promote(p, task.open_todos)
