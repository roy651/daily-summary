"""Feedback channel — parse Avigail's corrections (docs/04-delivery.md).

Captured AND consumed (run_digest applies it). Two inputs: the edited todo file (checkbox state + ``#
archive:`` / ``# revive:`` / ``# suppress:`` / ``# notes:`` directives) and an email reply body
(``done:`` / ``archive:`` / ``revive:`` / ``suppress:`` lines, rest treated as freeform → knowledge).
Records persist to ``state/feedback/``.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from digest_core.schema import Correction

_CHECKED = re.compile(r"^\s*-\s*\[[xX]\]\s*(.+?)\s*$")
_UNCHECKED = re.compile(r"^\s*-\s*\[\s\]\s*(.+?)\s*$")
_MARKER = re.compile(r"\s*<!--.*?-->\s*$")


@dataclass
class FeedbackRecord:
    run_date: str
    revised_todos: list[str] = field(
        default_factory=list
    )  # still-open / edited / added items
    eod_actuals: list[str] = field(
        default_factory=list
    )  # what got done (checked / "done:")
    suppressed_threads: list[str] = field(
        default_factory=list
    )  # threads Avigail flagged off
    archived_projects: list[str] = field(
        default_factory=list
    )  # project ids she confirmed done/dormant -> archive
    revived_projects: list[str] = field(
        default_factory=list
    )  # project ids to bring back to active
    corrections: list[Correction] = field(
        default_factory=list
    )  # retract-knowledge / merge-contacts reconciliations (# forget: / # alias:)
    freeform_notes: str = ""

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> FeedbackRecord:
        return cls(**json.loads(Path(path).read_text(encoding="utf-8")))


def _clean(line: str) -> str:
    """Strip the trailing <!-- marker --> from a rendered todo line."""
    return _MARKER.sub("", line).strip()


def _thread_ids(rest: str) -> list[str]:
    return [tid for tid in re.split(r"[,\s]+", rest.strip()) if tid]


def _parse_alias(rest: str) -> tuple[list[str], str | None]:
    """`a@x, b@y = subcontractor` -> (["a@x","b@y"], "subcontractor"). Role optional."""
    role: str | None = None
    if "=" in rest:
        rest, raw_role = rest.rsplit("=", 1)
        role = raw_role.strip().lower() or None
    return _thread_ids(rest), role


# Boundary of the quoted/original message in an email reply — her actual feedback is the text ABOVE it
# (top-posting). Covers English ("On … wrote:"), Hebrew ("… כתב/ה:"), Outlook headers, and quote lines.
_QUOTE_BOUNDARY = re.compile(
    r"^\s*(>|on .+wrote:|.*כתב/ה:|-{2,}\s*original message|from:\s|sent from my )",
    re.IGNORECASE,
)


def _strip_quoted(body: str) -> str:
    """Keep only the new reply text, dropping the quoted original (so the whole digest she replied to
    doesn't get swept into freeform_notes)."""
    kept: list[str] = []
    for line in body.splitlines():
        if _QUOTE_BOUNDARY.match(line):
            break
        kept.append(line)
    return "\n".join(kept).strip()


def parse_todos_md(text: str, *, run_date: str) -> FeedbackRecord:
    fb = FeedbackRecord(run_date=run_date)
    notes: list[str] = []
    in_feedback = (
        False  # once past the "## ✎ Feedback" heading, plain prose is treated as a note
    )
    in_comment = False  # skip <!-- ... --> help blocks entirely
    for line in text.splitlines():
        s = line.strip()
        if in_comment:
            if "-->" in s:
                in_comment = False
            continue
        if s.startswith("<!--"):
            if "-->" not in s:
                in_comment = True
            continue
        low = s.lower()
        if low.startswith("#") and "feedback" in low:
            in_feedback = True
            continue
        if m := _CHECKED.match(line):
            fb.eod_actuals.append(_clean(m.group(1)))
        elif m := _UNCHECKED.match(line):
            fb.revised_todos.append(_clean(m.group(1)))
        elif low.startswith("# suppress:"):
            fb.suppressed_threads.extend(_thread_ids(s.split(":", 1)[1]))
        elif low.startswith("# archive:"):
            fb.archived_projects.extend(_thread_ids(s.split(":", 1)[1]))
        elif low.startswith("# revive:"):
            fb.revived_projects.extend(_thread_ids(s.split(":", 1)[1]))
        elif low.startswith("# forget:"):
            if match := s.split(":", 1)[1].strip():
                fb.corrections.append(Correction(kind="retract_knowledge", match=match))
        elif low.startswith("# alias:"):
            emails, role = _parse_alias(s.split(":", 1)[1])
            if emails:
                fb.corrections.append(
                    Correction(kind="merge_contacts", emails=emails, role=role)
                )
        elif low.startswith(("# notes:", "# note:")):
            if note := s.split(":", 1)[1].strip():
                notes.append(note)
        elif in_feedback and s and not s.startswith("#"):
            # forgiving capture: free text she typed under the Feedback section becomes a note, so a
            # correction never silently vanishes just because it lacked the exact `# notes:` prefix.
            notes.append(s)
    fb.freeform_notes = " ".join(notes)
    return fb


def parse_reply(body: str, *, run_date: str) -> FeedbackRecord:
    fb = FeedbackRecord(run_date=run_date)
    notes: list[str] = []
    for line in _strip_quoted(body).splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if lower.startswith("done:"):
            fb.eod_actuals.append(stripped.split(":", 1)[1].strip())
        elif lower.startswith("suppress:"):
            fb.suppressed_threads.extend(_thread_ids(stripped.split(":", 1)[1]))
        elif lower.startswith("archive:"):
            fb.archived_projects.extend(_thread_ids(stripped.split(":", 1)[1]))
        elif lower.startswith("revive:"):
            fb.revived_projects.extend(_thread_ids(stripped.split(":", 1)[1]))
        elif lower.startswith("forget:"):
            if match := stripped.split(":", 1)[1].strip():
                fb.corrections.append(Correction(kind="retract_knowledge", match=match))
        elif lower.startswith("alias:"):
            emails, role = _parse_alias(stripped.split(":", 1)[1])
            if emails:
                fb.corrections.append(
                    Correction(kind="merge_contacts", emails=emails, role=role)
                )
        else:
            notes.append(stripped)
    fb.freeform_notes = " ".join(notes)
    return fb
