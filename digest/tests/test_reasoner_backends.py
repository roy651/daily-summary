"""Reasoner backends — Code (claude -p) + provider-agnostic Api (Anthropic / OpenAI-compatible).

All backends produce the SAME ModelOutput from the same packet, so they are drop-in equivalent. These
tests inject the runner/client so nothing hits the network or shells out.
"""

import json
import types

import pytest

from digest_core.reasoner import (
    MODEL_OUTPUT_SCHEMA,
    ApiReasoner,
    CodeReasoner,
    SessionPending,
    _parse_model_output,
    select_reasoner,
)

RUN = "2026-06-06"
OUT = {
    "project_updates": [
        {"project_id": "p1", "status_agent": "active", "evidence_thread_ids": ["t1"]}
    ],
    "digest_updates": [{"headline": "Something happened", "importance": "med"}],
    "unresolved": [],
    "insights": [{"scope": "general", "note": "a fact"}],
}


# ── shared contract ──


def test_schema_is_serializable_and_complete():
    json.dumps(MODEL_OUTPUT_SCHEMA)  # must round-trip for tool/function calling
    assert set(MODEL_OUTPUT_SCHEMA["required"]) == {
        "project_updates",
        "digest_updates",
        "unresolved",
        "insights",
    }


def test_parse_stamps_generated_at():
    out = _parse_model_output(dict(OUT), RUN)
    assert out.generated_at == RUN
    assert out.project_updates[0].project_id == "p1"


# ── CodeReasoner (claude -p), runner injected ──


def test_code_reasoner_consumes_and_archives(tmp_path):
    packet_path = tmp_path / "packet.json"
    output_path = tmp_path / "model_output.json"

    def fake_runner(_prompt):
        output_path.write_text(json.dumps({**OUT, "generated_at": RUN}))

    r = CodeReasoner(
        packet_path=packet_path,
        output_path=output_path,
        run_date=RUN,
        runner=fake_runner,
    )
    out = r.reason({"run_date": RUN, "threads": []})
    assert out.project_updates[0].project_id == "p1"
    # single-use: raw output archived, packet deleted
    assert (tmp_path / f"model_output.{RUN}.json").exists()
    assert not output_path.exists()
    assert not packet_path.exists()


def test_code_reasoner_errors_when_no_output_written(tmp_path):
    r = CodeReasoner(
        packet_path=tmp_path / "packet.json",
        output_path=tmp_path / "model_output.json",
        run_date=RUN,
        runner=lambda _p: None,  # claude wrote nothing
    )
    with pytest.raises(RuntimeError, match="produced no"):
        r.reason({"run_date": RUN})


def test_code_reasoner_rejects_wrong_day_stamp(tmp_path):
    output_path = tmp_path / "model_output.json"
    r = CodeReasoner(
        packet_path=tmp_path / "packet.json",
        output_path=output_path,
        run_date=RUN,
        runner=lambda _p: output_path.write_text(
            json.dumps({**OUT, "generated_at": "2025-01-01"})
        ),
    )
    with pytest.raises(SessionPending):
        r.reason({"run_date": RUN})


# ── ApiReasoner, client injected ──


class _FakeAnthropic:
    class messages:  # noqa: N801
        @staticmethod
        def create(**kwargs):
            block = types.SimpleNamespace(
                type="tool_use", name="emit_digest", input=dict(OUT)
            )
            return types.SimpleNamespace(content=[block])


def test_api_reasoner_anthropic_tool_call():
    r = ApiReasoner(run_date=RUN, provider="anthropic", client=_FakeAnthropic())
    out = r.reason({"run_date": RUN, "threads": []})
    assert out.digest_updates[0].headline == "Something happened"
    assert out.generated_at == RUN


class _FakeOpenAI:
    class chat:  # noqa: N801
        class completions:  # noqa: N801
            @staticmethod
            def create(**kwargs):
                msg = types.SimpleNamespace(content=json.dumps(OUT))
                return types.SimpleNamespace(
                    choices=[types.SimpleNamespace(message=msg)]
                )


def test_api_reasoner_openai_compatible_json():
    r = ApiReasoner(
        run_date=RUN,
        provider="openai",
        model="anthropic/claude-opus-4",
        client=_FakeOpenAI(),
    )
    out = r.reason({"run_date": RUN})
    assert out.insights[0].scope == "general"


def test_api_reasoner_rejects_unknown_provider():
    r = ApiReasoner(run_date=RUN, provider="grok", client=object())
    with pytest.raises(RuntimeError, match="unknown LLM_PROVIDER"):
        r.reason({})


# ── selection by env ──


def test_select_reasoner_routes_by_env(tmp_path):
    code = select_reasoner({"REASONER": "code"}, work_dir=tmp_path, run_date=RUN)
    assert isinstance(code, CodeReasoner)
    api = select_reasoner(
        {
            "REASONER": "api",
            "LLM_PROVIDER": "openai",
            "LLM_BASE_URL": "https://openrouter.ai/api/v1",
        },
        work_dir=tmp_path,
        run_date=RUN,
    )
    assert isinstance(api, ApiReasoner) and api.provider == "openai"
