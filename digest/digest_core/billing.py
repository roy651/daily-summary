"""Billing-direction role signal (C2) — invoices/receipts are the cleanest role signal there is:

  * an invoice/receipt ISSUED by Avigail/ULA (OUTBOUND) -> the counterparty is a CLIENT (a payer);
  * an invoice/receipt billed TO Avigail/ULA (INBOUND)  -> the counterparty is a SUBCONTRACTOR/vendor.

Detection is structural (billing-ESP senders + invoice/receipt terms, incl. Hebrew). Direction and the
counterparty come from the self-addresses (who sent / who received). For a direct invoice the
counterparty is the non-self party; for a billing-ESP *notification* (e.g. morning.co) the real
counterparty is named only in the subject/body, so we leave those to the reasoner rather than
mis-tagging the ESP. These threads are never dropped by the marketing denoise (see partition_marketing).
"""

from __future__ import annotations

from email.utils import parseaddr

from mail_evidence.records import EvidenceRecord, Thread

# Hebrew: חשבונית = (tax) invoice · קבלה = receipt · חשבונית מס = tax invoice · דרישת תשלום = payment demand.
_BILLING_TERMS = (
    "invoice",
    "receipt",
    "חשבונית",
    "קבלה",
    "חשבונית מס",
    "דרישת תשלום",
)
# Israeli/global invoicing services. A notification from one is billing, but the ESP is NOT the party.
_BILLING_ESPS = (
    "morning.co",
    "greeninvoice.co.il",
    "icount.co.il",
    "sumit.co.il",
    "ezcount.co.il",
)


def _bare(addr: str | None) -> str:
    return (parseaddr(addr or "")[1] or "").strip().lower()


def looks_like_billing(record: EvidenceRecord) -> bool:
    """Structural: a billing-ESP sender, or an invoice/receipt term in the subject."""
    if record.source != "email":
        return False
    sender = (record.from_ or "").lower()
    if any(esp in sender for esp in _BILLING_ESPS):
        return True
    subject = (record.subject or "").lower()
    return any(term in subject for term in _BILLING_TERMS)


def billing_counterparty(
    thread: Thread, self_addresses: set[str]
) -> tuple[str, str] | None:
    """Return (counterparty_email, role) for a DIRECT invoice in this thread, else None.
    Outbound (from a self address) -> (recipient, 'client'); inbound (to a self address, from a
    non-ESP human) -> (sender, 'subcontractor'). ESP notifications return None (party is in the body)."""
    selfset = {a.lower() for a in self_addresses if a}

    def _is_self(addr: str) -> bool:
        a = _bare(addr)
        return bool(a) and any(s in a for s in selfset)

    for r in thread.records:
        if not looks_like_billing(r):
            continue
        # Skip replies/forwards: a "Re: … Invoices" acknowledgement is NOT an invoice the replier issued
        # (this is what mis-tagged Katie's reply as a sub). Only the original invoice carries direction.
        if (r.subject or "").strip().lower().startswith(("re:", "fwd:", "fw:")):
            continue
        frm = _bare(r.from_)
        if _is_self(r.from_):  # outbound invoice -> recipient is a client-side payer
            for to in r.to or []:
                cp = _bare(to)
                if cp and not _is_self(to):
                    return cp, "client"
        elif any(
            _is_self(t) for t in (r.to or [])
        ):  # inbound invoice -> sender is a sub
            if frm and not any(esp in frm for esp in _BILLING_ESPS):
                return frm, "subcontractor"
    return None


def apply_billing_signals(
    threads: list[Thread], contacts, knowledge, self_addresses, *, run_date: str
) -> list[str]:
    """Set the counterparty's role from billing direction (source 'billing' — overrides a model/auto
    guess, but not a human correction) and record the relational fact in knowledge. Returns the notes."""
    notes: list[str] = []
    selfset = {a.lower() for a in self_addresses if a}
    for t in threads:
        cp = billing_counterparty(t, selfset)
        if not cp:
            continue
        email, role = cp
        if role == "subcontractor":
            # Inbound invoice = strong: they bill ULA -> a vendor/sub. Override a model/auto guess.
            contacts.set_role(
                email, role="subcontractor", source="billing", reason="invoices ULA"
            )
            note = f"Billing: {email} invoices ULA -> subcontractor."
        elif contacts.role_of(email) in (None, "other"):
            # Outbound to an UNKNOWN contact -> a direct client/payer. (If the recipient is already a
            # known agent/client, we record NOTHING: an invoice to an agency agent like Jen/Katie is
            # SPRIG being billed via them, not that the agent is a client — don't assert a false fact.)
            contacts.set_role(
                email, role="client", source="billing", reason="invoiced by ULA"
            )
            note = f"Billing: ULA invoices {email} -> client."
        else:
            continue  # known agent/client recipient — agency-mediated billing, no role/fact change
        knowledge.add_general(note, date=run_date, source="billing")
        notes.append(note)
    return notes
