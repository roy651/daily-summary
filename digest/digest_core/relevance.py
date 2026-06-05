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


# Conservative, STRUCTURAL marketing/bulk signals only (N2). Deliberately NOT keyed off language or
# generic "newsletter" wording — that risks false-positives against real Hebrew-speaking clients,
# violating recall-is-the-gate. We demote only on automated-sender patterns + known ESP domains.
_MARKETING_LOCALPARTS = (
    "no-reply",
    "noreply",
    "no_reply",
    "donotreply",
    "do-not-reply",
    "mailer-daemon",
    "newsletter",
    "newsletters",
    "notifications",
    "notification",
    "mailer",
)
_MARKETING_DOMAINS = (
    "flashyapp.com",
    "flashy.app",
    "customer.io",
    "vresp.com",
    "web-view.net",
    "shopifyemail.com",
    "emktng.shutterstock.com",
    "mailchimp.com",
    "list-manage.com",
    "sendgrid.net",
    "mailgun.org",
    "sparkpostmail.com",
    "sendinblue.com",
    "klaviyomail.com",
    "hubspotemail.net",
)


def looks_like_marketing(record: EvidenceRecord) -> bool:
    """A single record carrying a structural bulk/marketing signal (sender pattern, ESP domain, or the
    fetch layer's is_bulk header flag). Conservative by design."""
    if record.source != "email":
        return False
    if record.is_bulk:
        return True
    sender = (record.from_ or "").strip().lower()
    if "@" not in sender:
        return False
    local, _, domain = sender.partition("@")
    if any(p in local for p in _MARKETING_LOCALPARTS):
        return True
    return any(domain == d or domain.endswith("." + d) for d in _MARKETING_DOMAINS)


def partition_marketing(threads: list[Thread]) -> tuple[list[Thread], list[Thread]]:
    """Split threads into (kept, dropped). A thread is dropped ONLY if every record looks like
    marketing — mirroring mail-evidence's all-bulk rule, so a single human reply keeps the thread."""
    kept: list[Thread] = []
    dropped: list[Thread] = []
    for t in threads:
        if t.records and all(looks_like_marketing(r) for r in t.records):
            dropped.append(t)
        else:
            kept.append(t)
    return kept, dropped
