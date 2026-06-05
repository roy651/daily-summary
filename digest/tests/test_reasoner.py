"""Reasoner seam: Session / Api / Replay (docs/05-model-seam.md).

The seam is swapped by env with no code change. Replay is the offline test stand-in; Session is the
supervised v1 default (writes packet.json, reads back model_output.json); Api is phase-2 and must
fail cleanly when its optional dependency is absent.
"""

import json

import pytest

from digest_core.reasoner import (
    ApiReasoner,
    ReplayReasoner,
    SessionPending,
    SessionReasoner,
    select_reasoner,
)
from digest_core.schema import ModelOutput

PACKET = {"run_date": "2026-06-05", "threads": [], "current_projects": []}
OUTPUT = {"project_updates": [{"project_id": "p1", "status_agent": "active"}]}


def test_replay_reasoner_loads_fixture(tmp_path):
    path = tmp_path / "model_output.json"
    path.write_text(json.dumps(OUTPUT))
    out = ReplayReasoner(path).reason(PACKET)
    assert isinstance(out, ModelOutput)
    assert out.project_updates[0].project_id == "p1"


def test_session_reasoner_writes_packet_and_pends_when_no_output(tmp_path):
    r = SessionReasoner(
        packet_path=tmp_path / "packet.json", output_path=tmp_path / "model_output.json"
    )
    with pytest.raises(SessionPending):
        r.reason(PACKET)
    # The packet was written for the in-session model to read.
    assert (
        json.loads((tmp_path / "packet.json").read_text())["run_date"] == "2026-06-05"
    )


def test_session_reasoner_loads_output_when_present(tmp_path):
    (tmp_path / "model_output.json").write_text(json.dumps(OUTPUT))
    r = SessionReasoner(
        packet_path=tmp_path / "packet.json", output_path=tmp_path / "model_output.json"
    )
    out = r.reason(PACKET)
    assert out.project_updates[0].status_agent == "active"


def test_api_reasoner_fails_clearly_without_dependency():
    # The `anthropic` dep lives in the optional `api` extra; absent it, the error must be actionable.
    with pytest.raises(RuntimeError, match="api"):
        ApiReasoner().reason(PACKET)


def test_select_reasoner_by_env(tmp_path):
    (tmp_path / "model_output.json").write_text(json.dumps(OUTPUT))
    r = select_reasoner(
        {"REASONER": "replay"},
        work_dir=tmp_path,
        replay_path=tmp_path / "model_output.json",
    )
    assert isinstance(r, ReplayReasoner)
    r2 = select_reasoner({"REASONER": "session"}, work_dir=tmp_path)
    assert isinstance(r2, SessionReasoner)
