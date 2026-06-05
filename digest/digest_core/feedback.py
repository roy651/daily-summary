"""Feedback channel — parse Avigail's corrections (docs/04-delivery.md).

Captured in v1, consumed in phase 2. Two inputs: the edited todo file (checkbox state + ``#
suppress:`` / ``# notes:`` directives) and an email reply body (``done:`` / ``suppress:`` lines, rest
treated as freeform). Records persist to ``state/feedback/``.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

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


def parse_todos_md(text: str, *, run_date: str) -> FeedbackRecord:
    fb = FeedbackRecord(run_date=run_date)
    notes: list[str] = []
    for line in text.splitlines():
        if m := _CHECKED.match(line):
            fb.eod_actuals.append(_clean(m.group(1)))
        elif m := _UNCHECKED.match(line):
            fb.revised_todos.append(_clean(m.group(1)))
        elif line.lower().startswith("# suppress:"):
            fb.suppressed_threads.extend(_thread_ids(line.split(":", 1)[1]))
        elif line.lower().startswith("# notes:"):
            notes.append(line.split(":", 1)[1].strip())
    fb.freeform_notes = " ".join(notes)
    return fb


def parse_reply(body: str, *, run_date: str) -> FeedbackRecord:
    fb = FeedbackRecord(run_date=run_date)
    notes: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if lower.startswith("done:"):
            fb.eod_actuals.append(stripped.split(":", 1)[1].strip())
        elif lower.startswith("suppress:"):
            fb.suppressed_threads.extend(_thread_ids(stripped.split(":", 1)[1]))
        else:
            notes.append(stripped)
    fb.freeform_notes = " ".join(notes)
    return fb
