"""Delivery backends: File (default) + Email (flag-off) (docs/04-delivery.md).

FileDelivery writes the digest + editable todo file and reads edits back as feedback. EmailDelivery
must enforce the one invariant — recipient = Avigail only — and never send under DRY_RUN.
"""

import pytest

from digest_core.delivery import EmailDelivery, FileDelivery, select_delivery


def test_file_delivery_deliver_is_no_op_send(tmp_path):
    # The pipeline (run_digest) writes the artifacts now; the file backend's deliver is a no-op send.
    d = FileDelivery(out_dir=tmp_path)
    result = d.deliver("# digest\n", "# todos\n", run_date="2026-06-05")
    assert result.sent is True and result.backend == "file"
    assert not (tmp_path / "digest_2026-06-05.md").exists()


def test_file_delivery_collect_feedback_reads_edits(tmp_path):
    # The edited todos.md (written by the pipeline) is read back as feedback.
    (tmp_path / "todos.md").write_text(
        "# todos\n## Urgent\n- [x] [self] done thing  (ivory) <!-- p2 -->\n",
        encoding="utf-8",
    )
    feedback = FileDelivery(out_dir=tmp_path).collect_feedback(run_date="2026-06-05")
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


def test_digest_md_renders_to_html_for_mac_mail():
    from digest_core.delivery import _md_to_html

    html = _md_to_html(
        "## 📬 Email updates\n#### sprig — logo\n- **Assets received** — from Katie\n"
    )
    assert (
        "<html>" in html and "<style>" in html
    )  # self-contained doc Mac Mail can render
    assert "<h2" in html and "<h4" in html and "<li>" in html
    assert "<strong>Assets received</strong>" in html
    # the email's feedback hint is plain prose — no stray heading (that's why email drops the editable
    # todos template, whose `# archive:` lines would render as <h1>s)
    from digest_core.delivery import _FEEDBACK_HINT

    assert "<h1" not in _md_to_html(_FEEDBACK_HINT)


def test_select_delivery_defaults_to_file(tmp_path):
    d = select_delivery({}, out_dir=tmp_path)
    assert isinstance(d, FileDelivery)


def test_select_delivery_email_requires_recipient(tmp_path):
    with pytest.raises(ValueError):
        select_delivery({"DELIVERY": "email"}, out_dir=tmp_path)  # no DIGEST_EMAIL_TO
