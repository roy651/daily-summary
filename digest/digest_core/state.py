"""Domain state model — clients, projects, tasks, todos (docs/01-state-model.md).

Storage is JSON, one file per entity type, under ``state/`` (a deliberate divergence from the
sibling's CSV — our entities are nested and ragged, and the MODEL PASS returns JSON so ``apply`` is
a near-isomorphic merge). The load/write functions round-trip exactly: a written file re-loads to
an equal object graph, ``None`` <-> ``null`` preserved, field order stable so ``git diff`` of state
is reviewable.

Three-way separation (borrowed from the sibling's ledger): *observed-truth* (what the evidence
shows), *agent-proposed* (the model's read, rewritten each run), *human-confirmed* (Avigail's
overrides, written ONLY via the feedback channel — never by the deterministic layer).

Hierarchy: Project -> Task -> Todo. Tasks are optional; a Todo attaches to a Task when the model is
confident of the grouping, else hangs directly off the Project.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# ── controlled vocabularies ─────────────────────────────────────────────────────
# Extensible-but-checked: unknown values are rejected at construction so a typo in model output or
# a hand-edit fails loudly rather than silently creating a junk category. Revisit with Avigail.
TODO_CATEGORIES = frozenset({"self", "verify_subcontractor", "communicate_client"})
PROJECT_STATUSES = frozenset({"active", "on_hold", "blocked", "done", "archived"})
TASK_STATUSES = frozenset({"active", "on_hold", "blocked", "done"})
OWNERS = frozenset({"self", "subcontractor", "client_action"})
BLOCKER_KINDS = frozenset(
    {
        "awaiting_client_material",
        "awaiting_consent",
        "awaiting_subcontractor",
        "awaiting_payment",
        "external",
        "other",
    }
)


def _check(value: str, allowed: frozenset[str], field_name: str) -> None:
    if value not in allowed:
        raise ValueError(
            f"invalid {field_name}: {value!r} (allowed: {sorted(allowed)})"
        )


# ── leaf shapes ──────────────────────────────────────────────────────────────────


@dataclass
class Observation:
    """Soft, unstructured tacit knowledge. The landing zone for corrections + the future learning store."""

    date: str
    source: str  # "email" | "transcript" | "manual" | "feedback" | ...
    note: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Observation:
        return cls(date=d["date"], source=d["source"], note=d["note"])


@dataclass
class ManagingContact:
    """For an agency client (e.g. SPRIG), the agent(s) Avigail works through."""

    name: str
    email: str
    role_note: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ManagingContact:
        return cls(name=d["name"], email=d["email"], role_note=d.get("role_note", ""))


@dataclass
class Blocker:
    kind: str
    description: str
    since: str
    blocks_until: str | None = None

    def __post_init__(self) -> None:
        _check(self.kind, BLOCKER_KINDS, "blocker kind")

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Blocker:
        return cls(
            kind=d["kind"],
            description=d["description"],
            since=d["since"],
            blocks_until=d.get("blocks_until"),
        )


@dataclass
class Todo:
    """A concrete next-action for the next day or two. The model proposes; todos.py ranks."""

    text: str
    category: str
    target: str | None  # the sub / client / agent to act with (None for `self`)
    due_hint: str | None
    rationale: str
    source_thread_id: str | None

    def __post_init__(self) -> None:
        _check(self.category, TODO_CATEGORIES, "todo category")

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Todo:
        return cls(
            text=d["text"],
            category=d["category"],
            target=d.get("target"),
            due_hint=d.get("due_hint"),
            rationale=d.get("rationale", ""),
            source_thread_id=d.get("source_thread_id"),
        )


@dataclass
class Task:
    task_id: str
    title: str
    status: str
    owner: str
    subcontractor: str | None = None
    deadline: str | None = None
    blockers: list[Blocker] = field(default_factory=list)
    open_todos: list[Todo] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)

    def __post_init__(self) -> None:
        _check(self.status, TASK_STATUSES, "task status")
        _check(self.owner, OWNERS, "task owner")

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Task:
        return cls(
            task_id=d["task_id"],
            title=d["title"],
            status=d["status"],
            owner=d["owner"],
            subcontractor=d.get("subcontractor"),
            deadline=d.get("deadline"),
            blockers=[Blocker.from_dict(b) for b in d.get("blockers", [])],
            open_todos=[Todo.from_dict(t) for t in d.get("open_todos", [])],
            observations=[Observation.from_dict(o) for o in d.get("observations", [])],
        )


# ── Project ────────────────────────────────────────────────────────────────────


@dataclass
class Project:
    # Identity / classification
    project_id: str
    client_id: str
    title: str
    description: str = ""
    end_client: str | None = None
    assignee: str = "self"  # primary owner of the next action
    subcontractor: str | None = None
    contact_channel: str = "agent"  # "agent" | "direct" | "subcontractor_cc"

    # Lifecycle
    status: str = "active"
    status_reason: str = ""
    deadline: str | None = None
    deadline_kind: str | None = None  # "hard" | "soft" | None
    blockers: list[Blocker] = field(default_factory=list)
    last_activity_date: str | None = None  # OBSERVED-TRUTH (max evidence date)
    last_seen_run: str | None = None

    # Agent-proposed read (rewritten each run by the MODEL PASS)
    status_agent: str | None = None
    status_evidence: str = ""
    confidence: str | None = None  # "high" | "med" | "low"
    evidence_thread_ids: list[str] = field(default_factory=list)

    # Human-confirmed (written ONLY via the feedback/override channel — never by apply.py)
    status_confirmed: str | None = None
    confirmed_note: str | None = None

    # Work
    tasks: list[Task] = field(default_factory=list)
    open_todos: list[Todo] = field(
        default_factory=list
    )  # project-level todos not under a task
    observations: list[Observation] = field(default_factory=list)
    notes: str = ""

    def __post_init__(self) -> None:
        _check(self.status, PROJECT_STATUSES, "project status")
        _check(self.assignee, OWNERS, "project assignee")

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Project:
        return cls(
            project_id=d["project_id"],
            client_id=d["client_id"],
            title=d["title"],
            description=d.get("description", ""),
            end_client=d.get("end_client"),
            assignee=d.get("assignee", "self"),
            subcontractor=d.get("subcontractor"),
            contact_channel=d.get("contact_channel", "agent"),
            status=d.get("status", "active"),
            status_reason=d.get("status_reason", ""),
            deadline=d.get("deadline"),
            deadline_kind=d.get("deadline_kind"),
            blockers=[Blocker.from_dict(b) for b in d.get("blockers", [])],
            last_activity_date=d.get("last_activity_date"),
            last_seen_run=d.get("last_seen_run"),
            status_agent=d.get("status_agent"),
            status_evidence=d.get("status_evidence", ""),
            confidence=d.get("confidence"),
            evidence_thread_ids=list(d.get("evidence_thread_ids", [])),
            status_confirmed=d.get("status_confirmed"),
            confirmed_note=d.get("confirmed_note"),
            tasks=[Task.from_dict(t) for t in d.get("tasks", [])],
            open_todos=[Todo.from_dict(t) for t in d.get("open_todos", [])],
            observations=[Observation.from_dict(o) for o in d.get("observations", [])],
            notes=d.get("notes", ""),
        )


# ── ClientProfile ──────────────────────────────────────────────────────────────


@dataclass
class ClientProfile:
    client_id: str
    display_name: str
    is_agency: bool = False
    language: str = "he"
    status: str = "active"  # "active" | "archived"
    managing_contacts: list[ManagingContact] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)
    notes: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ClientProfile:
        return cls(
            client_id=d["client_id"],
            display_name=d["display_name"],
            is_agency=d.get("is_agency", False),
            language=d.get("language", "he"),
            status=d.get("status", "active"),
            managing_contacts=[
                ManagingContact.from_dict(m) for m in d.get("managing_contacts", [])
            ],
            observations=[Observation.from_dict(o) for o in d.get("observations", [])],
            notes=d.get("notes", ""),
        )


# ── JSON persistence ─────────────────────────────────────────────────────────────
# `asdict` emits dicts in field-definition order, so output is deterministic without sort_keys;
# None is preserved as JSON null. A trailing newline + 2-space indent keep diffs reviewable.


def _dump(items: list[Any], path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps([asdict(i) for i in items], indent=2, ensure_ascii=False)
    p.write_text(text + "\n", encoding="utf-8")


def _load(path: str | Path) -> list[dict[str, Any]]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_projects(projects: list[Project], path: str | Path) -> None:
    _dump(projects, path)


def load_projects(path: str | Path) -> list[Project]:
    return [Project.from_dict(d) for d in _load(path)]


def write_clients(clients: list[ClientProfile], path: str | Path) -> None:
    _dump(clients, path)


def load_clients(path: str | Path) -> list[ClientProfile]:
    return [ClientProfile.from_dict(d) for d in _load(path)]
