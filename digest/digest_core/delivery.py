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


# Appended to the emailed digest: a one-line nudge on how to reply with feedback (the email reply is
# her correction channel until the phase-2 web page). Kept short so it doesn't re-bloat the digest.
_FEEDBACK_HINT = (
    "\n\n---\n\n_Reply to this email to update me — e.g. `done: <todo>`, "
    "`archive: <project>`, `suppress: <thread>`, or just tell me in plain words._\n"
)

_EMAIL_CSS = (
    "body{font-family:-apple-system,BlinkMacSystemFont,Helvetica,Arial,sans-serif;"
    "font-size:14px;line-height:1.5;color:#222;max-width:720px;margin:0 auto;padding:8px}"
    "h1{font-size:20px;margin:0 0 12px}"
    "h2{font-size:17px;border-bottom:1px solid #eee;padding-bottom:3px;margin:22px 0 8px}"
    "h3{font-size:13px;color:#777;text-transform:uppercase;letter-spacing:.04em;margin:14px 0 4px}"
    "h4{font-size:14px;color:#1a7a4c;margin:12px 0 4px}"
    "ul{margin:4px 0 10px;padding-left:20px}li{margin:3px 0}"
    "code{background:#f4f4f4;padding:1px 4px;border-radius:3px;font-size:13px}"
    "hr{border:0;border-top:1px solid #eee;margin:18px 0}"
)


def _md_to_html(body_md: str) -> str:
    """Render the digest markdown to a self-contained HTML document so it displays in Mac Mail (which
    otherwise shows the raw markdown)."""
    import markdown

    html = markdown.markdown(body_md, extensions=["extra", "sane_lists"])
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<style>{_EMAIL_CSS}</style></head><body>{html}</body></html>"
    )


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

    def collect_feedback(self, *, run_date: str, threads=None) -> FeedbackRecord | None:
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

        # Email is for READING — send the digest itself (it already has the Todos section) plus a short
        # reply-feedback hint, NOT the editable todos file (its `# archive:` template would render as
        # giant H1s in HTML, and it's redundant here). The file backend keeps the editable todos.md.
        self._send_smtp(recipient, subject, digest_md + _FEEDBACK_HINT)
        return DeliveryResult(backend="email", sent=True, detail=f"sent to {recipient}")

    def _send_smtp(self, recipient: str, subject: str, body_md: str) -> None:
        import smtplib
        from email.message import EmailMessage

        msg = EmailMessage()
        msg["From"] = self.user
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.set_content(body_md)  # plain-text fallback (the markdown source)
        msg.add_alternative(
            _md_to_html(body_md), subtype="html"
        )  # what Mac Mail renders
        # Timeout so a scheduled/unattended run can't hang forever on a stuck SMTP connection (F9).
        with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=30) as smtp:
            smtp.login(self.user, self.password)
            smtp.send_message(msg)

    def collect_feedback(
        self, *, run_date: str, threads=None, reply_body: str | None = None
    ) -> FeedbackRecord | None:
        """Find Avigail's reply to the digest among the pulled threads and parse its directives. A reply
        is a record FROM her address whose subject carries our digest tag but does NOT start with it
        (i.e. it's an ``Re: digest: …``, not the outbound digest itself). The latest such reply wins.
        ``reply_body`` lets a caller/test pass an extracted body directly."""
        if reply_body is not None:
            return parse_reply(reply_body, run_date=run_date)
        if not threads:
            return None
        tag = self.SUBJECT_TAG.lower()
        replies = [
            r
            for t in threads
            for r in t.records
            if self.to in (r.from_ or "").lower()
            and tag in (r.subject or "").lower()
            and not (r.subject or "").strip().lower().startswith(tag)
        ]
        if not replies:
            return None
        latest = max(replies, key=lambda r: r.date)
        return parse_reply(latest.body_text or "", run_date=run_date)


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
