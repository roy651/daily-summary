"""ModelOutput — the contract the MODEL PASS must satisfy (docs/05-model-seam.md).

Parsing validates loudly: unknown enum values and missing required fields raise here, before
apply.py touches state. The model proposes; the deterministic layer applies — so this is where we
refuse to let bad output through.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from digest_core.state import (
    DEADLINE_KINDS,
    PROJECT_STATUSES,
    Blocker,
    Todo,
    _check,
    _check_optional,
    _require,
)

CONFIDENCES = frozenset({"high", "med", "low"})
IMPORTANCES = frozenset({"high", "med", "low"})


@dataclass
class ProjectUpdate:
    project_id: (
        str | None
    )  # None => newly discovered project (client_id + title then required)
    status_agent: str | None = None
    status_evidence: str = ""
    confidence: str | None = None
    evidence_thread_ids: list[str] = field(default_factory=list)
    # None = field omitted (keep existing blockers); [] = explicitly clear them (F6).
    blockers: list[Blocker] | None = None
    todos: list[Todo] = field(default_factory=list)
    # Todos the model judged COMPLETED this run (closure signal: approval/delivery/receipt/invoice).
    # Matched by text against the project's open todos and removed by apply. The close half of "add".
    closed_todos: list[str] = field(default_factory=list)
    # Soft tacit knowledge about this project (free-text notes); appended to project.observations.
    observations: list[str] = field(default_factory=list)
    deadline: str | None = None
    deadline_kind: str | None = None
    # The model saw the project fully invoiced this run (billed-in-full). With ~7d silence -> auto-archive.
    billed: bool = False
    # Required only for new projects (project_id is None):
    client_id: str | None = None
    end_client: str | None = None
    title: str | None = None
    assignee: str | None = None
    subcontractor: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ProjectUpdate:
        project_id = d.get("project_id")
        if project_id is None:
            if not d.get("client_id") or not d.get("title"):
                raise ValueError(
                    "new project (project_id=null) requires client_id and title"
                )
        status_agent = d.get("status_agent")
        if status_agent is not None:
            _check(status_agent, PROJECT_STATUSES, "status_agent")
        confidence = d.get("confidence")
        if confidence is not None:
            _check(confidence, CONFIDENCES, "confidence")
        _check_optional(d.get("deadline_kind"), DEADLINE_KINDS, "deadline_kind")
        blockers = (
            [Blocker.from_dict(b) for b in d["blockers"]] if "blockers" in d else None
        )
        return cls(
            project_id=project_id,
            status_agent=status_agent,
            status_evidence=d.get("status_evidence", ""),
            confidence=confidence,
            evidence_thread_ids=list(d.get("evidence_thread_ids", [])),
            blockers=blockers,
            todos=[Todo.from_dict(t) for t in d.get("todos", [])],
            closed_todos=list(d.get("closed_todos", [])),
            deadline=d.get("deadline"),
            deadline_kind=d.get("deadline_kind"),
            billed=bool(d.get("billed", False)),
            observations=list(d.get("observations", [])),
            client_id=d.get("client_id"),
            end_client=d.get("end_client"),
            title=d.get("title"),
            assignee=d.get("assignee"),
            subcontractor=d.get("subcontractor"),
        )


@dataclass
class DigestUpdate:
    headline: str
    detail: str
    importance: str
    project_id: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DigestUpdate:
        importance = d.get("importance", "med")
        _check(importance, IMPORTANCES, "importance")
        return cls(
            headline=_require(d, "headline", "digest_update"),
            detail=d.get("detail", ""),
            importance=importance,
            project_id=d.get("project_id"),
        )


# How an unplaced/flagged thread is routed in the digest:
#   unplaced = business thread the model couldn't attach to a project (needs your eye)
#   personal = non-business human mail (invitation, RSVP, appointment, family) — always surfaced
#   lead     = a possible new business inquiry
#   entity   = a new/ambiguous person-or-role decision the model wants confirmed (e.g. "treating X as a sub")
UNRESOLVED_KINDS = frozenset({"unplaced", "personal", "lead", "entity"})


@dataclass
class Unresolved:
    thread_id: str
    why: str
    kind: str = "unplaced"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Unresolved:
        kind = d.get("kind", "unplaced")
        _check(kind, UNRESOLVED_KINDS, "unresolved kind")
        return cls(
            thread_id=_require(d, "thread_id", "unresolved"),
            why=d.get("why", ""),
            kind=kind,
        )


@dataclass
class Insight:
    """A tacit-knowledge note. scope = "general" (-> knowledge store) or a client_id (-> that client)."""

    scope: str
    note: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Insight:
        return cls(
            scope=_require(d, "scope", "insight"), note=_require(d, "note", "insight")
        )


@dataclass
class ModelOutput:
    generated_at: str | None = None
    project_updates: list[ProjectUpdate] = field(default_factory=list)
    digest_updates: list[DigestUpdate] = field(default_factory=list)
    unresolved: list[Unresolved] = field(default_factory=list)
    insights: list[Insight] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ModelOutput:
        return cls(
            generated_at=d.get("generated_at"),
            project_updates=[
                ProjectUpdate.from_dict(p) for p in d.get("project_updates", [])
            ],
            digest_updates=[
                DigestUpdate.from_dict(u) for u in d.get("digest_updates", [])
            ],
            unresolved=[Unresolved.from_dict(u) for u in d.get("unresolved", [])],
            insights=[Insight.from_dict(i) for i in d.get("insights", [])],
        )
