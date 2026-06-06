"""Email feedback collection: find Avigail's reply to the digest among the pulled threads, strip the
quoted original, parse her directives — and keep the reply out of the reasoner's evidence."""

import types
from datetime import datetime

from digest_core.delivery import EmailDelivery
from digest_core.feedback import _strip_quoted
from digest_core.relevance import is_self_generated

ADDR = "avigail@ula.co.il"


def _rec(from_, subject, body="", day=6):
    return types.SimpleNamespace(
        from_=from_, subject=subject, body_text=body, date=datetime(2026, 6, day, 12, 0)
    )


def _thread(*recs):
    return types.SimpleNamespace(records=list(recs))


def _email():
    return EmailDelivery(
        to=ADDR, smtp_host="x", smtp_port=465, user="u", password="p", dry_run=True
    )


# ── reply detection + parsing ──

REPLY_BODY = (
    "done: Fix the associated typo in the Apreo header banner\n"
    "archive: sprig-new-website-proposal-jennie-prospect\n"
    "Rock Design is just Idan my web dev — same person as idandamti, not a separate vendor.\n"
    "\n"
    "On 6 Jun 2026, at 09:00, Avigail Marsha <avigail@ula.co.il> wrote:\n"
    "> # Daily digest — 2026-06-06\n"
    "> ## Project status ... (the whole quoted digest)\n"
)


def test_collect_feedback_finds_and_parses_her_reply():
    threads = [
        _thread(_rec("Charlene <charlene@sprigconsulting.com>", "TurnCare forms")),
        # the outbound digest landing back in the inbox — NOT a reply (subject starts with the tag)
        _thread(
            _rec("avigail.studio@gmail.com", "digest: 2026-06-06 — your daily digest")
        ),
        # her actual reply
        _thread(
            _rec(
                "Avigail Marsha <avigail@ula.co.il>",
                "Re: digest: 2026-06-06 — your daily digest",
                REPLY_BODY,
            )
        ),
    ]
    fb = _email().collect_feedback(run_date="2026-06-06", threads=threads)
    assert fb is not None
    assert fb.eod_actuals == ["Fix the associated typo in the Apreo header banner"]
    assert fb.archived_projects == ["sprig-new-website-proposal-jennie-prospect"]
    assert "Rock Design" in fb.freeform_notes
    assert "quoted digest" not in fb.freeform_notes  # the quoted original was stripped


def test_collect_feedback_none_without_a_reply():
    threads = [_thread(_rec("client@x.com", "a normal email"))]
    assert _email().collect_feedback(run_date="2026-06-06", threads=threads) is None


# ── quote stripping ──


def test_strip_quoted_drops_the_original():
    body = "my new note\nmore note\nOn 6 Jun 2026, at 09:00, X wrote:\n> old stuff"
    assert _strip_quoted(body) == "my new note\nmore note"


def test_strip_quoted_handles_hebrew_reply_marker():
    body = "תקן את זה\nב-2 ביוני 2026, בשעה 23:57, Nurit כתב/ה:\n> ציטוט"
    assert _strip_quoted(body) == "תקן את זה"


# ── her reply must not be read as evidence ──


def test_reply_to_digest_is_self_generated():
    r = types.SimpleNamespace(
        source="email", subject="Re: digest: 2026-06-06 — your daily digest"
    )
    assert is_self_generated(r) is True


def test_outbound_digest_is_self_generated():
    r = types.SimpleNamespace(
        source="email", subject="digest: 2026-06-06 — your daily digest"
    )
    assert is_self_generated(r) is True


def test_real_client_mail_is_not_self_generated():
    r = types.SimpleNamespace(source="email", subject="Re: RhythMedix logo")
    assert is_self_generated(r) is False


def test_self_generated_requires_self_sender_when_addresses_given():
    # H6: with self_addresses, only mail FROM Avigail counts as self-generated — a client thread that
    # happens to be subject-named 'digest:' must NOT be dropped (recall-is-the-gate).
    selfset = {"avigail@ula.co.il", "avigail.studio@gmail.com"}
    ours = types.SimpleNamespace(
        source="email", subject="digest: 2026-06-06", from_="avigail.studio@gmail.com"
    )
    client = types.SimpleNamespace(
        source="email", subject="Re: digest: pricing question", from_="client@acme.com"
    )
    assert is_self_generated(ours, self_addresses=selfset) is True
    assert is_self_generated(client, self_addresses=selfset) is False
