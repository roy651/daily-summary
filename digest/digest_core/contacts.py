"""DigestContactStore — the consumer's ContactStore for mail-evidence (docs/01, docs/05).

Persisted to ``state/contacts.json`` as ``{email: {role, source, reason, added}}``. Implements the
``mail_evidence.ContactStore`` protocol (``is_known`` / ``role_of`` / ``add_auto``) plus an explicit
``add`` used to seed roles during bootstrap. Roles are richer than the sibling's bare "other"
because role feeds the reasoning packet.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from email.utils import parseaddr
from pathlib import Path

CONTACT_ROLES = frozenset({"client", "agent", "subcontractor", "end_client", "other"})


def _norm_email(raw: str) -> str:
    """Lowercase, and reduce a 'Name <addr>' form to the bare address."""
    addr = parseaddr(raw)[1] or raw
    return addr.strip().lower()


@dataclass
class ContactEntry:
    role: str
    source: str  # "bootstrap" | "auto" | "manual"
    reason: str = ""
    added: str | None = (
        None  # ISO date when known; None keeps writes deterministic without a clock
    )


class DigestContactStore:
    def __init__(self, contacts: dict[str, ContactEntry] | None = None) -> None:
        self._contacts: dict[str, ContactEntry] = dict(contacts or {})

    # ── ContactStore protocol ──
    def is_known(self, email: str) -> bool:
        return _norm_email(email) in self._contacts

    def role_of(self, email: str) -> str | None:
        entry = self._contacts.get(_norm_email(email))
        return entry.role if entry else None

    def add_auto(self, email: str, reason: str) -> None:
        """Promote a previously-unknown human (called by mail_evidence.condition on T2 promotion)."""
        self.add(email, role="other", source="auto", reason=reason)

    # ── consumer-side seeding ──
    def add(
        self,
        email: str,
        *,
        role: str,
        source: str,
        reason: str = "",
        added: str | None = None,
    ) -> None:
        if role not in CONTACT_ROLES:
            raise ValueError(
                f"invalid contact role: {role!r} (allowed: {sorted(CONTACT_ROLES)})"
            )
        key = _norm_email(email)
        # Don't downgrade a known role to "other" on a later auto-promotion.
        existing = self._contacts.get(key)
        if existing and source == "auto" and existing.role != "other":
            return
        self._contacts[key] = ContactEntry(
            role=role, source=source, reason=reason, added=added
        )

    def entry(self, email: str) -> ContactEntry | None:
        return self._contacts.get(_norm_email(email))

    def items(self) -> list[tuple[str, ContactEntry]]:
        return sorted(self._contacts.items())

    # ── persistence ──
    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {email: asdict(entry) for email, entry in self.items()}
        p.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    @classmethod
    def load(cls, path: str | Path) -> DigestContactStore:
        p = Path(path)
        if not p.exists():
            return cls()
        raw = json.loads(p.read_text(encoding="utf-8"))
        contacts = {email: ContactEntry(**entry) for email, entry in raw.items()}
        return cls(contacts)
