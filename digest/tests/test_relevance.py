"""KeepAllHumanJudge + is_self_generated (docs/05, docs/04).

Recall is the gate: losing an important email is the worst failure, so the judge keeps every T2
human thread and lets the MODEL PASS decide. The only deterministic drop is our OWN prior digest
(when EmailDelivery is on, the digest lands back in the inbox and must not be read as evidence).
"""

from datetime import datetime, timezone

from mail_evidence import RelevanceDecision, Thread
from mail_evidence.records import EvidenceRecord

from digest_core.relevance import KeepAllHumanJudge, is_self_generated


def _email(subject, from_="someone@example.com", body="hi"):
    return EvidenceRecord(
        id="m1",
        thread_id="t1",
        source="email",
        date=datetime(2026, 6, 5, tzinfo=timezone.utc),
        body_text=body,
        from_=from_,
        to=["avigail@ula.example"],
        subject=subject,
    )


def test_keepall_judge_keeps_every_thread():
    thread = Thread(thread_id="t1", records=[_email("New project inquiry")], tier="T2")
    decision = KeepAllHumanJudge().is_relevant(thread)
    assert isinstance(decision, RelevanceDecision)
    assert decision.relevant is True
    assert (
        decision.promote_emails == []
    )  # promotion is decided downstream, not by the judge


def test_self_generated_digest_is_detected():
    rec = _email(
        "digest: 2026-06-05 — your morning summary", from_="avigail@ula.example"
    )
    assert is_self_generated(rec, digest_subject_tag="digest:")


def test_real_mail_is_not_self_generated():
    rec = _email("Re: homepage mockup", from_="agent@sprig.example")
    assert not is_self_generated(rec, digest_subject_tag="digest:")


def test_self_generated_tag_is_case_insensitive():
    rec = _email("DIGEST: 2026-06-05")
    assert is_self_generated(rec, digest_subject_tag="digest:")


def test_transcript_is_never_self_generated():
    rec = EvidenceRecord(
        id="transcripts/call",
        thread_id="transcripts/call",
        source="transcript",
        date=datetime(2026, 6, 5, tzinfo=timezone.utc),
        body_text="we agreed on the logo",
        subject=None,
    )
    assert not is_self_generated(rec, digest_subject_tag="digest:")
