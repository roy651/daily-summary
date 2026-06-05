"""build_reasoning_packet — the pure-data input to the MODEL PASS (docs/05-model-seam.md).

The packet bundles the running state the model updates (projects, clients, contacts) with the
recent evidence (cleaned threads). It is plain JSON-serializable data: ``SessionReasoner`` writes it
to ``packet.json``; tests assert its shape. No formatting here — that's ``render.py``.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from mail_evidence.records import Thread

from digest_core.contacts import DigestContactStore
from digest_core.evidence import direction_of
from digest_core.state import ClientProfile, Project

# A type alias for documentation; the packet is canonically a JSON-able dict (it is serialized).
ReasoningPacket = dict[str, Any]

# Projects in these terminal states are not fed to the model (kept in state, but not re-surfaced).
_PACKET_HIDDEN_STATUSES = frozenset({"done", "archived"})
_MAX_EVIDENCE_IDS = 25

GLOSSARY = (
    "Avigail is a freelance designer (studio 'ula'). Her biggest client, SPRIG, is an AGENCY with "
    "its own end-clients: she usually works through a SPRIG agent but sometimes with the end-client "
    "directly. Her subcontractors usually work through her but sometimes deal with clients directly "
    "and CC her. Projects vary: some have hard deadlines, many are long-running and frequently "
    "on-hold awaiting client material, consent, or another blocker."
)


def _todo_brief(todo) -> dict[str, Any]:
    return {
        "text": todo.text,
        "category": todo.category,
        "target": todo.target,
        "due_hint": todo.due_hint,
    }


def _blocker_brief(b) -> dict[str, Any]:
    return {"kind": b.kind, "description": b.description, "since": b.since}


def _project_brief(p: Project) -> dict[str, Any]:
    return {
        "project_id": p.project_id,
        "client_id": p.client_id,
        "end_client": p.end_client,
        "title": p.title,
        "description": p.description,
        "assignee": p.assignee,
        "subcontractor": p.subcontractor,
        "contact_channel": p.contact_channel,
        "status": p.status,
        "status_reason": p.status_reason,
        "deadline": p.deadline,
        "deadline_kind": p.deadline_kind,
        "blockers": [_blocker_brief(b) for b in p.blockers],
        "last_activity_date": p.last_activity_date,
        # Cap to the most recent ids so the packet doesn't bloat monotonically over months (F2).
        "evidence_thread_ids": list(p.evidence_thread_ids)[-_MAX_EVIDENCE_IDS:],
        "open_todos": [_todo_brief(t) for t in p.open_todos],
        "tasks": [
            {
                "task_id": t.task_id,
                "title": t.title,
                "status": t.status,
                "owner": t.owner,
                "deadline": t.deadline,
                "open_todos": [_todo_brief(td) for td in t.open_todos],
            }
            for t in p.tasks
        ],
    }


def _client_brief(c: ClientProfile) -> dict[str, Any]:
    return {
        "client_id": c.client_id,
        "display_name": c.display_name,
        "is_agency": c.is_agency,
        "status": c.status,
        "managing_contacts": [
            {"name": m.name, "email": m.email} for m in c.managing_contacts
        ],
    }


def _thread_brief(t: Thread, self_addresses: Iterable[str]) -> dict[str, Any]:
    return {
        "thread_id": t.thread_id,
        "tier": t.tier,
        "relevance_reason": t.relevance.reason if t.relevance else None,
        "records": [
            {
                "date": r.date.isoformat(),
                "direction": direction_of(r, self_addresses),
                "from_": r.from_,
                "to": list(r.to),
                "cc": list(r.cc),
                "subject": r.subject,
                "body_text": r.body_text,
                "attachments": [a.filename for a in r.attachments_meta],
            }
            for r in t.records
        ],
    }


def build_reasoning_packet(
    *,
    run_date: str,
    since: str,
    until: str,
    projects: list[Project],
    clients: list[ClientProfile],
    contacts: DigestContactStore,
    threads: list[Thread],
    self_addresses: Iterable[str],
    glossary: str = GLOSSARY,
) -> ReasoningPacket:
    self_addresses = set(self_addresses)
    return {
        "run_date": run_date,
        "window": {"since": since, "until": until},
        "current_projects": [
            _project_brief(p)
            for p in projects
            if p.status not in _PACKET_HIDDEN_STATUSES
        ],
        "clients": [_client_brief(c) for c in clients],
        "contacts": [
            {"email": email, "role": entry.role} for email, entry in contacts.items()
        ],
        "threads": [_thread_brief(t, self_addresses) for t in threads],
        "glossary": glossary,
    }
