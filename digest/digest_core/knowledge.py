"""General tacit-knowledge store — "how Avigail operates" (docs/01, learning layer).

Per-client and per-project soft knowledge lives on those entities' ``observations``. This store
holds the *general* insights that don't belong to a single client (Avigail's working patterns,
cross-client conventions, recurring vendors, name aliases). It is fed back into every reasoning
packet so each pass builds on what earlier passes learned.

This is the *capture + storage* half of the learning layer, brought forward so the historical
backfill accumulates knowledge rather than discarding it. The *feedback-driven* half (consuming
Avigail's corrections) remains phase 2.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from digest_core.state import Observation


class KnowledgeStore:
    def __init__(self, general: list[Observation] | None = None) -> None:
        self.general: list[Observation] = list(general or [])

    def _notes(self) -> set[str]:
        return {o.note.strip().lower() for o in self.general}

    def add_general(self, note: str, *, date: str, source: str = "agent") -> None:
        """Append a general insight, de-duplicated by note text (knowledge accretes, not repeats)."""
        if note.strip() and note.strip().lower() not in self._notes():
            self.general.append(
                Observation(date=date, source=source, note=note.strip())
            )

    def supersede(
        self,
        match: str,
        *,
        note: str | None = None,
        date: str,
        source: str = "feedback",
    ) -> int:
        """Correction primitive: REMOVE every general note containing ``match`` (case-insensitive) so a
        false fact doesn't linger, then optionally record the corrected ``note``. Returns the count
        removed. Used by both Avigail's feedback and the reasoner's own corrections."""
        m = match.strip().lower()
        if not m:
            return 0
        before = len(self.general)
        self.general = [o for o in self.general if m not in o.note.lower()]
        removed = before - len(self.general)
        if note:
            self.add_general(note, date=date, source=source)
        return removed

    def general_notes(self, *, mark_confirmed: bool = False) -> list[str]:
        """Notes for the reasoning packet. With ``mark_confirmed``, feedback-sourced notes (Avigail's
        own corrections) are tagged so the reasoner treats them as authoritative over its own guesses
        and over older contradicting notes."""
        out: list[str] = []
        for o in self.general:
            if mark_confirmed and o.source == "feedback":
                out.append(f"[AVIGAIL-CONFIRMED] {o.note}")
            else:
                out.append(o.note)
        return out

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {"general": [asdict(o) for o in self.general]}
        p.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    @classmethod
    def load(cls, path: str | Path) -> KnowledgeStore:
        p = Path(path)
        if not p.exists():
            return cls()
        raw = json.loads(p.read_text(encoding="utf-8"))
        return cls(general=[Observation.from_dict(o) for o in raw.get("general", [])])
