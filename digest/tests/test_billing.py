"""C2 — billing direction is the cleanest role signal. Detect invoices, infer the counterparty's role
from direction (outbound -> client, inbound -> sub), set it (overriding a model guess), and never let
the marketing denoise drop billing mail."""

from datetime import datetime, timezone

from mail_evidence.records import EvidenceRecord, Thread

from digest_core.billing import (
    apply_billing_signals,
    billing_counterparty,
    looks_like_billing,
)
from digest_core.contacts import DigestContactStore
from digest_core.knowledge import KnowledgeStore
from digest_core.relevance import partition_marketing

SELF = {"avigail@ula.co.il", "avigail.studio@gmail.com"}


def _rec(frm, to, subject, *, is_bulk=False):
    return EvidenceRecord(
        id=subject,
        thread_id=subject,
        source="email",
        date=datetime(2026, 6, 6, tzinfo=timezone.utc),
        body_text="",
        from_=frm,
        to=to,
        subject=subject,
        is_bulk=is_bulk,
    )


def _thread(rec):
    return Thread(thread_id=rec.thread_id, records=[rec], tier="T1", relevance=None)


def test_looks_like_billing_terms_and_esps():
    assert looks_like_billing(_rec("a@x.com", ["b@y.com"], "May Invoice"))
    assert looks_like_billing(
        _rec("notify@morning.co", ["avigail@ula.co.il"], "קבלה 439")
    )
    assert not looks_like_billing(_rec("a@x.com", ["b@y.com"], "RhythMedix logo"))


def test_outbound_invoice_recipient_is_client():
    t = _thread(_rec("avigail@ula.co.il", ["jen@sprigconsulting.com"], "May Invoice"))
    assert billing_counterparty(t, SELF) == ("jen@sprigconsulting.com", "client")


def test_inbound_invoice_sender_is_subcontractor():
    t = _thread(
        _rec("Lee <lee@illustrate.com>", ["avigail@ula.co.il"], "Invoice March")
    )
    assert billing_counterparty(t, SELF) == ("lee@illustrate.com", "subcontractor")


def test_esp_notification_has_no_direct_counterparty():
    # morning.co notification: the real party is in the subject/body, not from/to — leave to the model.
    t = _thread(
        _rec("notify@morning.co", ["avigail@ula.co.il"], "קבלה 439 - לי קורצווייל")
    )
    assert billing_counterparty(t, SELF) is None


def test_apply_billing_signals_sets_role_over_model_guess():
    c = DigestContactStore()
    c.add("jen@sprigconsulting.com", role="other", source="model")
    k = KnowledgeStore()
    t = _thread(_rec("avigail@ula.co.il", ["jen@sprigconsulting.com"], "May Invoice"))
    notes = apply_billing_signals([t], c, k, SELF, run_date="2026-06-06")
    assert c.role_of("jen@sprigconsulting.com") == "client"
    assert any("invoiced by ULA" in n for n in k.general_notes())
    assert notes


def test_billing_mail_is_never_denoised():
    # A billing notice from a no-reply/ESP sender must survive partition_marketing.
    t = _thread(
        _rec("notify@morning.co", ["avigail@ula.co.il"], "חשבונית 100", is_bulk=True)
    )
    kept, dropped = partition_marketing([t])
    assert kept and not dropped
