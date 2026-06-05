"""unify() — clean + chronologically order conditioned threads (docs/02-pipeline.md).

Drops our own delivered digests (so they're never read as evidence), removes threads that become
empty, sorts records within each thread by date, and tags each record's direction relative to
Avigail's own addresses.
"""

from datetime import datetime, timezone

from mail_evidence import Thread
from mail_evidence.records import EvidenceRecord

from digest_core.evidence import direction_of, unify

SELF = {"avigail@ula.example"}


def _rec(mid, day, from_, subject="hi"):
    return EvidenceRecord(
        id=mid,
        thread_id="t1",
        source="email",
        date=datetime(2026, 6, day, tzinfo=timezone.utc),
        body_text="body",
        from_=from_,
        to=["avigail@ula.example"]
        if from_ != "avigail@ula.example"
        else ["agent@sprig.example"],
        subject=subject,
    )


def test_unify_sorts_records_chronologically():
    t = Thread(
        thread_id="t1",
        records=[
            _rec("m2", 5, "agent@sprig.example"),
            _rec("m1", 3, "agent@sprig.example"),
        ],
        tier="T1",
    )
    [out] = unify([t], self_addresses=SELF)
    assert [r.id for r in out.records] == ["m1", "m2"]


def test_unify_drops_self_generated_digest_records():
    t = Thread(
        thread_id="t1",
        records=[
            _rec("m1", 3, "agent@sprig.example", subject="Re: logo"),
            _rec("m2", 4, "avigail@ula.example", subject="digest: 2026-06-04"),
        ],
        tier="T1",
    )
    [out] = unify([t], self_addresses=SELF)
    assert [r.id for r in out.records] == ["m1"]


def test_unify_drops_threads_emptied_by_filter():
    t = Thread(
        thread_id="t1",
        records=[_rec("m1", 3, "avigail@ula.example", subject="digest: 2026-06-03")],
        tier="T1",
    )
    assert unify([t], self_addresses=SELF) == []


def test_direction_inbound_vs_outbound():
    assert direction_of(_rec("m1", 3, "agent@sprig.example"), SELF) == "inbound"
    assert direction_of(_rec("m2", 3, "avigail@ula.example"), SELF) == "outbound"


def test_direction_transcript():
    rec = EvidenceRecord(
        id="transcripts/x",
        thread_id="x",
        source="transcript",
        date=datetime(2026, 6, 3, tzinfo=timezone.utc),
        body_text="call",
    )
    assert direction_of(rec, SELF) == "transcript"
