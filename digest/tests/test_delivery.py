"""Delivery backends: File (default) + Email (flag-off) (docs/04-delivery.md).

FileDelivery writes the digest + editable todo file and reads edits back as feedback. EmailDelivery
must enforce the one invariant — recipient = Avigail only — and never send under DRY_RUN.
"""

import pytest

from digest_core.delivery import EmailDelivery, FileDelivery, select_delivery


def test_file_delivery_writes_both_files(tmp_path):
    d = FileDelivery(out_dir=tmp_path)
    result = d.deliver("# digest\n", "# todos\n", run_date="2026-06-05")
    assert (tmp_path / "digest_2026-06-05.md").read_text() == "# digest\n"
    assert (tmp_path / "todos.md").read_text() == "# todos\n"
    assert result.sent is True


def test_file_delivery_collect_feedback_reads_edits(tmp_path):
    d = FileDelivery(out_dir=tmp_path)
    d.deliver(
        "# digest\n",
        "# todos\n## Urgent\n- [x] [self] done thing  (ivory) <!-- p2 -->\n",
        run_date="2026-06-05",
    )
    feedback = d.collect_feedback(run_date="2026-06-05")
    assert feedback is not None
    assert any("done thing" in t for t in feedback.eod_actuals)


def test_email_delivery_rejects_non_allowlist_recipient(tmp_path):
    d = EmailDelivery(
        to="avigail@ula.example",
        smtp_host="smtp.x",
        smtp_port=465,
        user="u",
        password="p",
        dry_run=True,
    )
    with pytest.raises(ValueError, match="recipient"):
        d.deliver(
            "# digest\n",
            "# todos\n",
            run_date="2026-06-05",
            override_to="client@evil.example",
        )


def test_email_delivery_dry_run_does_not_send(tmp_path):
    d = EmailDelivery(
        to="avigail@ula.example",
        smtp_host="smtp.x",
        smtp_port=465,
        user="u",
        password="p",
        dry_run=True,
    )
    result = d.deliver("# digest\n", "# todos\n", run_date="2026-06-05")
    assert result.sent is False  # would-send only
    assert "avigail@ula.example" in result.detail


def test_select_delivery_defaults_to_file(tmp_path):
    d = select_delivery({}, out_dir=tmp_path)
    assert isinstance(d, FileDelivery)


def test_select_delivery_email_requires_recipient(tmp_path):
    with pytest.raises(ValueError):
        select_delivery({"DELIVERY": "email"}, out_dir=tmp_path)  # no DIGEST_EMAIL_TO
