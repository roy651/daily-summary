"""Relevance judge + self-generated-mail filter (docs/04, docs/05).

KeepAllHumanJudge keeps every T2 (unknown-human) thread — recall is the gate, and the MODEL PASS
labels relevance with full context. ``is_self_generated`` is the one deterministic drop: when the
digest is delivered by email it lands back in the inbox, and must never be read as evidence.
"""

from __future__ import annotations

from mail_evidence import RelevanceDecision
from mail_evidence.records import EvidenceRecord, Thread


class KeepAllHumanJudge:
    """Keep every T2 human thread; promotion to a known contact is decided downstream, not here."""

    def is_relevant(self, thread: Thread) -> RelevanceDecision:
        return RelevanceDecision(
            relevant=True,
            reason="kept: surface all human threads; the model decides relevance",
            promote_emails=[],
        )


def is_self_generated(
    record: EvidenceRecord, *, digest_subject_tag: str = "digest:"
) -> bool:
    """True iff this record is one of our own delivered digests (recognized by its subject tag)."""
    if record.source != "email" or not record.subject:
        return False
    return record.subject.strip().lower().startswith(digest_subject_tag.strip().lower())
