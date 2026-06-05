"""Ground-truth scoring (docs/07-acceptance.md).

We have no invoice-style oracle, so quality is measured by recall against Avigail's per-day ground
truth: did the digest surface the things she says mattered? Recall is the gate; precision is
informational (over-surfacing is fine, she prunes).
"""

import json

from digest_core.evaluation import (
    GroundTruth,
    aggregate_recall,
    score_digest,
)

DIGEST = """# Daily digest — 2026-06-05
## Project status
- RhythMedix homepage — blocked
## Important updates (last 24h)
- New lead: tri-fold brochure (Studio Lev)
## TODO
- Ask Avi to forward the homepage copy
"""


def test_full_recall_when_all_present():
    gt = GroundTruth(
        date="2026-06-05",
        must_surface=[
            "RhythMedix homepage",
            "tri-fold brochure",
            "forward the homepage copy",
        ],
    )
    result = score_digest(DIGEST, gt)
    assert result.recall == 1.0
    assert result.missed == []


def test_partial_recall_lists_misses():
    gt = GroundTruth(
        date="2026-06-05",
        must_surface=["RhythMedix homepage", "logo variations", "invoice reminder"],
    )
    result = score_digest(DIGEST, gt)
    assert result.total == 3
    assert result.matched == 1
    assert set(result.missed) == {"logo variations", "invoice reminder"}
    assert abs(result.recall - 1 / 3) < 1e-9


def test_matching_is_case_insensitive():
    gt = GroundTruth(date="2026-06-05", must_surface=["rhythmedix HOMEPAGE"])
    assert score_digest(DIGEST, gt).recall == 1.0


def test_empty_gt_is_full_recall():
    assert (
        score_digest(DIGEST, GroundTruth(date="2026-06-05", must_surface=[])).recall
        == 1.0
    )


def test_aggregate_recall_across_days():
    r1 = score_digest(
        DIGEST, GroundTruth("2026-06-05", ["RhythMedix homepage", "missing"])
    )
    r2 = score_digest(DIGEST, GroundTruth("2026-06-06", ["tri-fold brochure"]))
    # 1 + 1 matched out of 2 + 1 total = 2/3
    assert abs(aggregate_recall([r1, r2]) - 2 / 3) < 1e-9


def test_ground_truth_load(tmp_path):
    path = tmp_path / "2026-06-05.json"
    path.write_text(json.dumps({"date": "2026-06-05", "must_surface": ["a", "b"]}))
    gt = GroundTruth.load(path)
    assert gt.date == "2026-06-05"
    assert gt.must_surface == ["a", "b"]
