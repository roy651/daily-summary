"""ModelOutput schema — parse + validate the MODEL PASS output (docs/05-model-seam.md).

Validation is the guard against a model returning junk: unknown enums and missing required fields
fail loudly here, before apply.py touches state.
"""

import pytest

from digest_core.schema import ModelOutput


def _minimal_update(**over):
    base = {
        "project_id": "p1",
        "status_agent": "active",
        "status_evidence": "saw activity in t-1",
        "confidence": "high",
        "evidence_thread_ids": ["t-1"],
        "todos": [],
    }
    base.update(over)
    return base


def test_parses_valid_output():
    out = ModelOutput.from_dict(
        {
            "project_updates": [
                _minimal_update(
                    todos=[
                        {
                            "text": "ask client",
                            "category": "communicate_client",
                            "target": "agent@sprig.example",
                            "rationale": "needs approval",
                        }
                    ],
                    blockers=[
                        {
                            "kind": "awaiting_consent",
                            "description": "approval",
                            "since": "2026-06-01",
                        }
                    ],
                )
            ],
            "digest_updates": [
                {
                    "project_id": "p1",
                    "headline": "Client asked for v2",
                    "detail": "...",
                    "importance": "high",
                }
            ],
            "unresolved": [{"thread_id": "t-9", "why": "unclear sender"}],
        }
    )
    assert out.project_updates[0].todos[0].category == "communicate_client"
    assert out.project_updates[0].blockers[0].kind == "awaiting_consent"
    assert out.digest_updates[0].importance == "high"
    assert out.unresolved[0].thread_id == "t-9"


def test_new_project_requires_client_and_title():
    with pytest.raises(ValueError):
        # project_id=None signals a new project, so client_id + title are required.
        ModelOutput.from_dict({"project_updates": [_minimal_update(project_id=None)]})


def test_new_project_ok_with_client_and_title():
    out = ModelOutput.from_dict(
        {
            "project_updates": [
                _minimal_update(project_id=None, client_id="sprig", title="New flyer")
            ]
        }
    )
    assert out.project_updates[0].project_id is None
    assert out.project_updates[0].title == "New flyer"


def test_unknown_status_rejected():
    with pytest.raises(ValueError):
        ModelOutput.from_dict(
            {"project_updates": [_minimal_update(status_agent="frozen")]}
        )


def test_unknown_confidence_rejected():
    with pytest.raises(ValueError):
        ModelOutput.from_dict(
            {"project_updates": [_minimal_update(confidence="pretty_sure")]}
        )


def test_unknown_importance_rejected():
    with pytest.raises(ValueError):
        ModelOutput.from_dict(
            {
                "project_updates": [],
                "digest_updates": [
                    {"headline": "x", "detail": "y", "importance": "critical"}
                ],
            }
        )


def test_empty_output_is_valid():
    out = ModelOutput.from_dict({})
    assert (
        out.project_updates == [] and out.digest_updates == [] and out.unresolved == []
    )
