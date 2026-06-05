"""The MODEL PASS seam — Session / Api / Replay (docs/05-model-seam.md).

One swappable interface: ``reason(packet) -> ModelOutput``. Selected by the ``REASONER`` env var so
the same pipeline runs supervised today and headless later with no code change.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from digest_core.schema import ModelOutput

ReasoningPacket = dict[str, Any]


class Reasoner(Protocol):
    def reason(self, packet: ReasoningPacket) -> ModelOutput: ...


class SessionPending(Exception):
    """Raised when the supervised model hasn't produced model_output.json yet — re-run after it has."""


class ReplayReasoner:
    """Offline/test stand-in: load a fixture ModelOutput, ignore the packet. Mirrors the sibling."""

    def __init__(self, output_path: str | Path) -> None:
        self.output_path = Path(output_path)

    def reason(self, packet: ReasoningPacket) -> ModelOutput:
        return ModelOutput.from_dict(
            json.loads(self.output_path.read_text(encoding="utf-8"))
        )


class SessionReasoner:
    """v1 default: write the packet for the in-session model; load its model_output.json when ready."""

    def __init__(self, *, packet_path: str | Path, output_path: str | Path) -> None:
        self.packet_path = Path(packet_path)
        self.output_path = Path(output_path)

    def reason(self, packet: ReasoningPacket) -> ModelOutput:
        if self.output_path.exists():
            return ModelOutput.from_dict(
                json.loads(self.output_path.read_text(encoding="utf-8"))
            )
        self.packet_path.parent.mkdir(parents=True, exist_ok=True)
        self.packet_path.write_text(
            json.dumps(packet, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        raise SessionPending(
            f"Packet written to {self.packet_path}. Produce {self.output_path} (the model pass), then re-run."
        )


class ApiReasoner:
    """Phase-2 headless pass via the Anthropic API. The `anthropic` dep lives in the `api` extra."""

    def __init__(
        self, *, model: str = "claude-opus-4-8", max_tokens: int = 8000
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens

    def reason(self, packet: ReasoningPacket) -> ModelOutput:
        try:
            import anthropic  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "ApiReasoner needs the optional 'api' extra: `uv sync --extra api` (installs anthropic)."
            ) from exc
        # Wiring the actual call (prompt assembly + tool-forced structured output) is a phase-2 task;
        # consult the claude-api reference for current model ids before enabling.
        raise NotImplementedError(
            "ApiReasoner is a phase-2 seam; not wired in the MVP."
        )


def select_reasoner(
    env: Mapping[str, str],
    *,
    work_dir: str | Path,
    replay_path: str | Path | None = None,
) -> Reasoner:
    mode = env.get("REASONER", "session").strip().lower()
    work_dir = Path(work_dir)
    if mode == "replay":
        path = (
            replay_path or env.get("REPLAY_OUTPUT") or (work_dir / "model_output.json")
        )
        return ReplayReasoner(path)
    if mode == "api":
        return ApiReasoner()
    return SessionReasoner(
        packet_path=work_dir / "packet.json", output_path=work_dir / "model_output.json"
    )
