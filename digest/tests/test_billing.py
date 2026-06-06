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


def test_reply_to_an_invoice_is_not_a_counterparty():
    # Katie's "Re: May Invoices" acknowledgement must NOT be read as an invoice she issued.
    t = _thread(_rec("katiea123@gmail.com", ["avigail@ula.co.il"], "Re: May Invoices"))
    assert billing_counterparty(t, SELF) is None


def test_outbound_fills_unknown_role_with_client():
    c = DigestContactStore()
    c.add("new@client.com", role="other", source="auto")
    k = KnowledgeStore()
    t = _thread(_rec("avigail@ula.co.il", ["new@client.com"], "May Invoice"))
    apply_billing_signals([t], c, k, SELF, run_date="2026-06-06")
    assert c.role_of("new@client.com") == "client"
    assert any("ULA invoices new@client.com" in n for n in k.general_notes())


def test_outbound_to_known_agent_records_no_fact():
    # Invoicing a SPRIG agent (Jen) is the AGENCY being billed via her — not a direct-client fact.
    c = DigestContactStore()
    c.add("jen@sprigconsulting.com", role="agent", source="model")
    k = KnowledgeStore()
    t = _thread(_rec("avigail@ula.co.il", ["jen@sprigconsulting.com"], "May Invoice"))
    notes = apply_billing_signals([t], c, k, SELF, run_date="2026-06-06")
    assert notes == []  # no misleading "Jen is invoiced by ULA" note
    assert c.role_of("jen@sprigconsulting.com") == "agent"  # unchanged
    assert not any("jen@sprigconsulting.com" in n for n in k.general_notes())


def test_outbound_does_not_downgrade_a_known_agent():
    # Avigail invoicing a SPRIG agent (Jen/Katie) must NOT turn the agent into a "client".
    c = DigestContactStore()
    c.add("jen@sprigconsulting.com", role="agent", source="model")
    k = KnowledgeStore()
    t = _thread(_rec("avigail@ula.co.il", ["jen@sprigconsulting.com"], "May Invoice"))
    apply_billing_signals([t], c, k, SELF, run_date="2026-06-06")
    assert c.role_of("jen@sprigconsulting.com") == "agent"  # unchanged


def test_inbound_invoice_overrides_model_guess_with_sub():
    c = DigestContactStore()
    c.add("lee@illustrate.com", role="other", source="model")
    k = KnowledgeStore()
    t = _thread(_rec("lee@illustrate.com", ["avigail@ula.co.il"], "Invoice 12"))
    apply_billing_signals([t], c, k, SELF, run_date="2026-06-06")
    assert c.role_of("lee@illustrate.com") == "subcontractor"


def test_billing_mail_is_never_denoised():
    # A billing notice from a no-reply/ESP sender must survive partition_marketing.
    t = _thread(
        _rec("notify@morning.co", ["avigail@ula.co.il"], "חשבונית 100", is_bulk=True)
    )
    kept, dropped = partition_marketing([t])
    assert kept and not dropped
