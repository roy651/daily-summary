"""Ground-truth scoring for the held-out-week backtest (docs/07-acceptance.md).

daily-summary has no pre-existing oracle, so we manufacture one: Avigail provides per-day
ground-truth phrases that the digest *must surface*. The scorer is recall-oriented (recall is the
gate, precision informational) — it reports what was missed so iteration has a target.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GroundTruth:
    date: str
    must_surface: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path) -> GroundTruth:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(date=d["date"], must_surface=list(d.get("must_surface", [])))


@dataclass
class ScoreResult:
    date: str
    total: int
    matched: int
    missed: list[str]

    @property
    def recall(self) -> float:
        return self.matched / self.total if self.total else 1.0


def score_digest(digest_md: str, gt: GroundTruth) -> ScoreResult:
    """Recall = fraction of GT phrases present (case-insensitive substring) in the rendered digest."""
    haystack = digest_md.lower()
    missed = [phrase for phrase in gt.must_surface if phrase.lower() not in haystack]
    return ScoreResult(
        date=gt.date,
        total=len(gt.must_surface),
        matched=len(gt.must_surface) - len(missed),
        missed=missed,
    )


def aggregate_recall(results: list[ScoreResult]) -> float:
    """Micro-averaged recall across days (total matched / total expected)."""
    total = sum(r.total for r in results)
    matched = sum(r.matched for r in results)
    return matched / total if total else 1.0
