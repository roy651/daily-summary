"""Delivery backends + selection (docs/04-delivery.md).

FileDelivery (default) writes the digest + an editable todo file and reads edits back as feedback.
EmailDelivery (built now, flag-off) sends the digest to Avigail's own address only — the one
invariant — and never sends on a --dry-run. Selection is by the ``DELIVERY`` env var.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from digest_core.feedback import FeedbackRecord, parse_reply, parse_todos_md


@dataclass
class DeliveryResult:
    backend: str
    sent: bool  # True = delivered/written; False = would-send only (dry-run)
    detail: str


class FileDelivery:
    """The no-send backend: the pipeline already wrote the digest + editable todos to out/, so delivery
    is a no-op here. Reads the edited todos back as feedback on the next run."""

    def __init__(self, out_dir: str | Path) -> None:
        self.out_dir = Path(out_dir)

    def deliver(
        self, digest_md: str, todos_md: str, *, run_date: str
    ) -> DeliveryResult:
        return DeliveryResult(
            backend="file", sent=True, detail=f"written to {self.out_dir}"
        )

    def collect_feedback(self, *, run_date: str) -> FeedbackRecord | None:
        todos = self.out_dir / "todos.md"
        if not todos.exists():
            return None
        return parse_todos_md(todos.read_text(encoding="utf-8"), run_date=run_date)


class EmailDelivery:
    """Send the digest by email to Avigail ONLY. Built now; enabled by DELIVERY=email."""

    SUBJECT_TAG = "digest:"

    def __init__(
        self,
        *,
        to: str,
        smtp_host: str,
        smtp_port: int,
        user: str,
        password: str,
        dry_run: bool = True,
    ) -> None:
        if not to:
            raise ValueError("EmailDelivery requires a recipient (DIGEST_EMAIL_TO)")
        self.to = to.strip().lower()
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.user = user
        self.password = password
        self.dry_run = dry_run

    def deliver(
        self,
        digest_md: str,
        todos_md: str,
        *,
        run_date: str,
        override_to: str | None = None,
    ) -> DeliveryResult:
        recipient = (override_to or self.to).strip().lower()
        # The one invariant: we only ever email Avigail herself, never a client/sub.
        if recipient != self.to:
            raise ValueError(
                f"refusing to send: recipient {recipient!r} is not the allowlisted address"
            )

        subject = f"{self.SUBJECT_TAG} {run_date} — your daily digest"
        if self.dry_run:
            return DeliveryResult(
                backend="email",
                sent=False,
                detail=f"dry-run: would send to {recipient}: {subject}",
            )

        self._send_smtp(recipient, subject, digest_md + "\n\n---\n\n" + todos_md)
        return DeliveryResult(backend="email", sent=True, detail=f"sent to {recipient}")

    def _send_smtp(self, recipient: str, subject: str, body: str) -> None:
        import smtplib
        from email.message import EmailMessage

        msg = EmailMessage()
        msg["From"] = self.user
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.set_content(body)
        # Timeout so a scheduled/unattended run can't hang forever on a stuck SMTP connection (F9).
        with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=30) as smtp:
            smtp.login(self.user, self.password)
            smtp.send_message(msg)

    def collect_feedback(
        self, *, run_date: str, reply_body: str | None = None
    ) -> FeedbackRecord | None:
        # In production the reply arrives as an inbound thread (read via mail-evidence). Here we accept
        # the already-extracted body; wiring the IMAP reply lookup is a daily.py/phase-2 concern.
        if reply_body is None:
            return None
        return parse_reply(reply_body, run_date=run_date)


def select_delivery(
    env: Mapping[str, str], *, out_dir: str | Path, dry_run: bool = False
) -> FileDelivery | EmailDelivery:
    """Pick the delivery backend by DELIVERY. ``dry_run`` (from the CLI --dry-run flag, the single
    preview knob) makes EmailDelivery report what it WOULD send without sending."""
    backend = env.get("DELIVERY", "file").strip().lower()
    if backend == "email":
        return EmailDelivery(
            to=env.get("DIGEST_EMAIL_TO", ""),
            smtp_host=env.get("SMTP_HOST", ""),
            smtp_port=int(env.get("SMTP_PORT", "465")),
            user=env.get("SMTP_USER", ""),
            password=env.get("SMTP_APP_PASSWORD", ""),
            dry_run=dry_run,
        )
    return FileDelivery(out_dir=out_dir)
