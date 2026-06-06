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
# Authority of a role's source, low→high. A correction may not DOWNGRADE to a weaker source:
# human (feedback/manual/bootstrap) > billing-direction > model/auto inference.
_SOURCE_RANK = {
    "auto": 0,
    "model": 0,
    "billing": 1,
    "bootstrap": 2,
    "manual": 2,
    "feedback": 2,
}


def _norm_email(raw: str) -> str:
    """Lowercase, and reduce a 'Name <addr>' form to the bare address."""
    addr = parseaddr(raw)[1] or raw
    return addr.strip().lower()


@dataclass
class ContactEntry:
    role: str
    source: str  # "bootstrap" | "auto" | "model" | "billing" | "feedback" | "manual"
    reason: str = ""
    added: str | None = (
        None  # ISO date when known; None keeps writes deterministic without a clock
    )
    alias_of: str | None = (
        None  # set when this address is another address of a canonical contact (entity merge)
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
        # Inferred sources (auto/model) never override an already-established specific role — they
        # can only fill in an unknown ("other") one. This keeps the first confident role sticky and
        # avoids run-to-run flip-flop; explicit sources (bootstrap/manual) always win.
        existing = self._contacts.get(key)
        if (
            existing
            and existing.role != "other"
            and source in ("auto", "model")
            and role != existing.role
        ):
            return
        self._contacts[key] = ContactEntry(
            role=role, source=source, reason=reason, added=added
        )

    def set_role(self, email: str, *, role: str, source: str, reason: str = "") -> None:
        """Correction primitive: force a role (bypasses the sticky-first-role guard), subject to source
        authority — a weaker source may not override a stronger one (human > billing > model/auto). So a
        model correction can't clobber a human-confirmed role or a billing-direction fact, but a human
        correction overrides anything. Used to reconcile a mis-identified entity / set a billing role."""
        if role not in CONTACT_ROLES:
            raise ValueError(
                f"invalid contact role: {role!r} (allowed: {sorted(CONTACT_ROLES)})"
            )
        key = _norm_email(email)
        existing = self._contacts.get(key)
        if existing and _SOURCE_RANK.get(source, 0) < _SOURCE_RANK.get(
            existing.source, 0
        ):
            return  # don't downgrade a stronger-sourced role
        self._contacts[key] = ContactEntry(role=role, source=source, reason=reason)

    def merge(
        self, emails: list[str], *, role: str | None, source: str, reason: str = ""
    ) -> None:
        """Physically link addresses that are ONE person/entity: the first becomes canonical, the rest
        point at it via ``alias_of`` (so the review surface shows one person, not several). Sets the
        shared role too (precedence-guarded). Used by merge_contacts corrections (the Idan case)."""
        keys = [_norm_email(e) for e in emails if _norm_email(e)]
        if not keys:
            return
        canonical = keys[0]
        for key in keys:
            if role:
                self.set_role(key, role=role, source=source, reason=reason)
            entry = self._contacts.get(key)
            if entry is None:
                entry = ContactEntry(role=role or "other", source=source, reason=reason)
                self._contacts[key] = entry
            entry.alias_of = None if key == canonical else canonical

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
