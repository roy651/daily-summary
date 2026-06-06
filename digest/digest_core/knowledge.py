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
import logging
import re
from dataclasses import asdict
from pathlib import Path

from digest_core.state import SOURCE_RANK, Observation

log = logging.getLogger("digest.knowledge")


def _norm_note(s: str) -> str:
    """Lowercase alphanumeric tokens joined by single spaces — a stable key for containment dedup."""
    return " ".join(re.findall(r"[a-z0-9]+", s.lower()))


class KnowledgeStore:
    def __init__(self, general: list[Observation] | None = None) -> None:
        self.general: list[Observation] = list(general or [])

    def add_general(self, note: str, *, date: str, source: str = "agent") -> None:
        """Append a general insight, with containment dedup so paraphrases don't pile up (K1): if an
        existing note already CONTAINS the new one (it adds nothing), skip; if the new note is a SUPERSET
        of an existing one, drop the shorter and keep the richer. (Genuinely different facts are kept —
        this is strict containment, not fuzzy matching; semantic dups are consolidated by the reasoner.)"""
        text = note.strip()
        if not text:
            return
        n = _norm_note(text)
        if not n:
            return
        new_rank = SOURCE_RANK.get(source, 0)
        kept: list[Observation] = []
        for o in self.general:
            eo = _norm_note(o.note)
            if n == eo or n in eo:  # an existing note already covers this -> don't add
                return
            # The new note is richer (a superset) -> replace the shorter existing — but only when the
            # writer outranks-or-equals it (M1). A model paraphrase must not drop a confirmed note;
            # in that case keep BOTH (the confirmed fact stands, the elaboration is appended).
            if eo in n and SOURCE_RANK.get(o.source, 0) <= new_rank:
                continue
            kept.append(o)
        kept.append(Observation(date=date, source=source, note=text))
        self.general = kept

    def supersede(
        self,
        match: str,
        *,
        note: str | None = None,
        date: str,
        source: str = "feedback",
    ) -> int:
        """Correction primitive: REMOVE every general note containing ``match`` (case-insensitive) whose
        source the writer outranks-or-equals (M1 — a model retract may not erase an Avigail-confirmed
        note), then optionally record the corrected ``note``. Returns the count removed; the removed
        texts are logged so the blast radius of an unanchored ``# forget:`` is visible (M3). Used by both
        Avigail's feedback and the reasoner's own corrections."""
        m = match.strip().lower()
        if not m:
            return 0
        rank = SOURCE_RANK.get(source, 0)

        def _removable(o: Observation) -> bool:
            return m in o.note.lower() and SOURCE_RANK.get(o.source, 0) <= rank

        gone = [o for o in self.general if _removable(o)]
        if gone:
            self.general = [o for o in self.general if not _removable(o)]
            log.info(
                "supersede(%r, source=%s): retracted %d note(s): %s",
                match,
                source,
                len(gone),
                "; ".join(o.note for o in gone),
            )
        if note:
            self.add_general(note, date=date, source=source)
        return len(gone)

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
