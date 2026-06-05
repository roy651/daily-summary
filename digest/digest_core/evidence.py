"""Evidence conditioning post-step: unify + clean conditioned threads (docs/02-pipeline.md).

mail-evidence already fetched, threaded, deduped, and tiered. This module applies daily-summary's
own cleanup before the packet: drop our own delivered digests, drop threads emptied by that, sort
records chronologically, and expose each record's direction relative to Avigail.

Later (phase 1.5) transcript EvidenceRecords flow through the same path — this is where the
multi-source streams are unified.
"""

from __future__ import annotations

from collections.abc import Iterable

from mail_evidence.records import EvidenceRecord, Thread

from digest_core.relevance import is_self_generated


def direction_of(record: EvidenceRecord, self_addresses: Iterable[str]) -> str:
    """'outbound' (from Avigail), 'inbound' (to her), or 'transcript'."""
    if record.source == "transcript":
        return "transcript"
    selves = {a.strip().lower() for a in self_addresses}
    sender = (record.from_ or "").strip().lower()
    return "outbound" if sender in selves else "inbound"


def unify(
    threads: list[Thread],
    *,
    self_addresses: Iterable[str],
    digest_subject_tag: str = "digest:",
) -> list[Thread]:
    """Return cleaned, chronologically-sorted threads; threads emptied by filtering are dropped."""
    cleaned: list[Thread] = []
    for t in threads:
        kept = [
            r
            for r in t.records
            if not is_self_generated(r, digest_subject_tag=digest_subject_tag)
        ]
        if not kept:
            continue
        kept.sort(key=lambda r: r.date)
        cleaned.append(
            Thread(
                thread_id=t.thread_id, records=kept, tier=t.tier, relevance=t.relevance
            )
        )
    return cleaned
