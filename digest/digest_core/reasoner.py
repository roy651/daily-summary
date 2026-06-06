"""The MODEL PASS seam — Session / Code / Api / Replay (docs/05-model-seam.md).

One swappable interface: ``reason(packet) -> ModelOutput``. Selected by the ``REASONER`` env var so
the same pipeline runs supervised today and headless later with no code change.

Backends (all produce the SAME ``ModelOutput`` from the same packet, so they are drop-in equivalent):
  * ``session`` — supervised in-session model writes ``model_output.json`` (default, MVP).
  * ``code``    — headless Claude Code (``claude -p``) under the user's subscription (no API key).
  * ``api``     — provider-agnostic cloud: ``LLM_PROVIDER=anthropic`` (Anthropic SDK, tool-forced) or
                  ``openai`` (any OpenAI-compatible endpoint — OpenRouter / Together / local — via
                  ``LLM_BASE_URL`` + ``LLM_MODEL`` + ``LLM_API_KEY``).
  * ``replay``  — load a fixture ``model_output.json`` (tests).

The model-facing contract (``_REASONER_SYSTEM`` + ``MODEL_OUTPUT_SCHEMA``) is shared by the Code and
Api backends so swapping providers is an env change, never a code change.
"""

from __future__ import annotations

import json
import logging
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from digest_core.schema import ModelOutput

ReasoningPacket = dict[str, Any]
log = logging.getLogger("digest.reasoner")


class Reasoner(Protocol):
    def reason(self, packet: ReasoningPacket) -> ModelOutput: ...


class SessionPending(Exception):
    """Raised when the supervised model hasn't produced model_output.json yet — re-run after it has."""


# ── shared model-facing contract (Code + Api backends) ───────────────────────────

# JSON Schema for ModelOutput — constrains the structured output for tool/function calling. Enums are
# pinned only on required, non-null fields (cross-provider safe); schema.py is the authoritative gate
# and re-validates everything loudly on parse.
_TODO_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "category": {
            "type": "string",
            "enum": ["self", "verify_subcontractor", "communicate_client"],
        },
        "target": {"type": ["string", "null"]},
        "due_hint": {"type": ["string", "null"]},
        "rationale": {"type": "string"},
        "source_thread_id": {"type": ["string", "null"]},
    },
    "required": ["text", "category"],
}
_BLOCKER_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {
            "type": "string",
            "enum": [
                "awaiting_client_material",
                "awaiting_consent",
                "awaiting_subcontractor",
                "awaiting_payment",
                "external",
                "other",
            ],
        },
        "description": {"type": "string"},
        "since": {"type": "string"},
        "blocks_until": {"type": ["string", "null"]},
    },
    "required": ["kind", "description", "since"],
}
MODEL_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "generated_at": {"type": "string"},
        "project_updates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "project_id": {"type": ["string", "null"]},
                    "client_id": {"type": ["string", "null"]},
                    "end_client": {"type": ["string", "null"]},
                    "title": {"type": ["string", "null"]},
                    "assignee": {"type": ["string", "null"]},
                    "subcontractor": {"type": ["string", "null"]},
                    "status_agent": {"type": ["string", "null"]},
                    "status_evidence": {"type": "string"},
                    "confidence": {"type": ["string", "null"]},
                    "evidence_thread_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "blockers": {"type": "array", "items": _BLOCKER_SCHEMA},
                    "todos": {"type": "array", "items": _TODO_SCHEMA},
                    "closed_todos": {"type": "array", "items": {"type": "string"}},
                    "observations": {"type": "array", "items": {"type": "string"}},
                    "deadline": {"type": ["string", "null"]},
                    "deadline_kind": {"type": ["string", "null"]},
                    "billed": {"type": "boolean"},
                },
            },
        },
        "digest_updates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "headline": {"type": "string"},
                    "detail": {"type": "string"},
                    "importance": {"type": "string", "enum": ["high", "med", "low"]},
                    "project_id": {"type": ["string", "null"]},
                },
                "required": ["headline", "importance"],
            },
        },
        "unresolved": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "thread_id": {"type": "string"},
                    "why": {"type": "string"},
                    "kind": {
                        "type": "string",
                        "enum": ["unplaced", "personal", "lead", "entity"],
                    },
                },
                "required": ["thread_id"],
            },
        },
        "insights": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "scope": {"type": "string"},
                    "note": {"type": "string"},
                },
                "required": ["scope", "note"],
            },
        },
    },
    "required": ["project_updates", "digest_updates", "unresolved", "insights"],
}

_REASONER_SYSTEM = (
    "You are the reasoning pass of Avigail's READ-ONLY daily business digest (freelance design studio "
    "'ula'). Input is a JSON packet: current_projects (carry-forward state), clients, contacts (with "
    "roles), threads (conditioned recent email), knowledge, and a glossary. Produce ONE ModelOutput "
    "object: project_updates, digest_updates, unresolved, insights.\n"
    "Rules:\n"
    "- ACTIVITY CONTRACT: emit a project_update ONLY for projects with genuine activity in this window, "
    "and cite the responsible thread ids in evidence_thread_ids. Do NOT re-state quiet/unchanged "
    "projects — they carry forward automatically and their silence is what lets them age to dormant. "
    "Activity is dated from the cited in-window evidence, never from merely mentioning a project.\n"
    "- CLOSURE (the 'remove' half): list completed todos verbatim in closed_todos; set "
    "status_agent='done' on delivery/approval/sign-off; set billed=true only when fully invoiced.\n"
    "- AUTHORITY: a knowledge note tagged [AVIGAIL-CONFIRMED] is a correction from Avigail herself — "
    "follow it over your own inference AND over any older/contradicting note (e.g. if she says two email "
    "addresses are the same person, treat them as one; do NOT re-assert they're distinct).\n"
    "- ENTITY ROLES (see the packet glossary): someone who INVOICES Avigail or whose output FEEDS her "
    "deliverables is a SUBCONTRACTOR; someone who COORDINATES on the agency side is an AGENT. Neither is "
    "a client — their work belongs as todos (verify_subcontractor / communicate_client) under the real "
    "client's project. SPRIG is an agency; SPRIG-direct work is client_id=sprig, end_client=null.\n"
    "- RECALL-FIRST: never drop a possibly-relevant human thread — surface low-confidence items in "
    "unresolved or as low-importance digest_updates. Losing an important email is the worst failure.\n"
    "- UNRESOLVED kinds (set 'kind' on each): 'personal' for non-business human mail (invitations, RSVPs, "
    "appointments, family, courses) — ALWAYS surface these, never drop them; 'lead' for a possible new "
    "business inquiry; 'entity' when you make a NEW or AMBIGUOUS person/role call you'd want Avigail to "
    "confirm (e.g. first time treating an address as a subcontractor, or two addresses that may be the "
    "same person); 'unplaced' (default) for a business thread you couldn't attach to a project.\n"
    "- Allowed enums: status active|on_hold|blocked|done|archived; todo category self|"
    "verify_subcontractor|communicate_client; confidence/importance high|med|low; deadline_kind "
    "hard|soft. Follow the packet's glossary for entity/role specifics."
)


def _parse_model_output(data: dict[str, Any], run_date: str) -> ModelOutput:
    """Stamp generated_at (if the model omitted it) and validate via the authoritative schema gate."""
    data = dict(data)
    data.setdefault("generated_at", run_date)
    return ModelOutput.from_dict(data)


def _write_packet(packet_path: Path, packet: ReasoningPacket) -> None:
    packet_path.parent.mkdir(parents=True, exist_ok=True)
    packet_path.write_text(
        json.dumps(packet, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _consume_output(output_path: Path, packet_path: Path, run_date: str) -> ModelOutput:
    """Validate model_output.json, then make it single-use: archive to model_output.<run_date>.json and
    delete the raw-body packet, so a later run can never silently re-apply a previous run's reasoning."""
    data = json.loads(output_path.read_text(encoding="utf-8"))
    stamped = data.get("generated_at")
    if stamped and stamped != run_date:
        raise SessionPending(
            f"{output_path} is stamped generated_at={stamped!r} but this run is {run_date!r}. "
            f"Remove/replace it with output for {run_date}, then re-run."
        )
    output = _parse_model_output(data, run_date)
    output_path.replace(output_path.with_suffix(f".{run_date}.json"))
    packet_path.unlink(missing_ok=True)
    return output


# ── backends ─────────────────────────────────────────────────────────────────────


class ReplayReasoner:
    """Offline/test stand-in: load a fixture ModelOutput, ignore the packet. Mirrors the sibling."""

    def __init__(self, output_path: str | Path) -> None:
        self.output_path = Path(output_path)

    def reason(self, packet: ReasoningPacket) -> ModelOutput:
        return ModelOutput.from_dict(
            json.loads(self.output_path.read_text(encoding="utf-8"))
        )


class SessionReasoner:
    """v1 default: write the packet for the in-session model; load its model_output.json when ready.

    The output is single-use (F1) — see ``_consume_output``. A ``generated_at`` in the output (if
    present) must match this run's date; a stale file for another day is refused, not consumed.
    """

    def __init__(
        self, *, packet_path: str | Path, output_path: str | Path, run_date: str
    ) -> None:
        self.packet_path = Path(packet_path)
        self.output_path = Path(output_path)
        self.run_date = run_date

    def reason(self, packet: ReasoningPacket) -> ModelOutput:
        if self.output_path.exists():
            return _consume_output(self.output_path, self.packet_path, self.run_date)
        _write_packet(self.packet_path, packet)
        raise SessionPending(
            f"Packet written to {self.packet_path}. Produce {self.output_path} "
            f"(stamp generated_at={self.run_date!r}), then re-run."
        )


class CodeReasoner:
    """Headless model pass via Claude Code (``claude -p``) under the user's Claude subscription — no API
    key, no per-token billing. Writes the packet, invokes ``claude`` to author model_output.json against
    the shared contract, then validates + single-use-consumes it. ``runner`` is injected in tests."""

    def __init__(
        self,
        *,
        packet_path: str | Path,
        output_path: str | Path,
        run_date: str,
        claude_bin: str = "claude",
        model: str | None = None,
        timeout: int = 900,
        runner=None,
    ) -> None:
        self.packet_path = Path(packet_path)
        self.output_path = Path(output_path)
        self.run_date = run_date
        self.claude_bin = claude_bin
        self.model = model
        self.timeout = timeout
        self._runner = runner or self._default_runner

    def reason(self, packet: ReasoningPacket) -> ModelOutput:
        _write_packet(self.packet_path, packet)
        # One reprompt-on-bad-output retry, so a single malformed pass (prose / code fence / wrong path)
        # doesn't lose the whole day's digest (H4). SessionPending (wrong-day stamp) is NOT retried.
        last_err = "no output file"
        for attempt in range(2):
            self.output_path.unlink(
                missing_ok=True
            )  # never consume a stale prior output
            self._runner(self._prompt(retry=attempt > 0))
            if not self.output_path.exists():
                last_err = f"`claude` produced no {self.output_path.name}"
                continue
            try:
                return _consume_output(
                    self.output_path, self.packet_path, self.run_date
                )
            except json.JSONDecodeError as exc:
                last_err = f"invalid JSON: {exc}"
            except ValueError as exc:  # schema.py rejected an enum / missing field
                last_err = f"invalid ModelOutput: {exc}"
        raise RuntimeError(
            f"CodeReasoner: `claude` did not produce valid model_output.json after a retry ({last_err}). "
            "Check that claude is logged in and allowed Read,Write."
        )

    def _prompt(self, *, retry: bool = False) -> str:
        retry_hint = (
            "Your previous attempt did not write a single valid JSON object — write ONLY the JSON, no "
            "prose, no code fence, no markdown. "
            if retry
            else ""
        )
        return (
            f"{retry_hint}Read {self.packet_path} — the reasoning packet for today's digest. Then write "
            f"{self.output_path} as a SINGLE JSON object (no prose, no code fence) conforming to the "
            f"ModelOutput schema (project_updates, digest_updates, unresolved, insights), with "
            f'"generated_at": "{self.run_date}".\n\n{_REASONER_SYSTEM}'
        )

    def _default_runner(self, prompt: str) -> None:
        cmd = [
            self.claude_bin,
            "-p",
            prompt,
            "--allowedTools",
            "Read,Write",
            "--add-dir",
            str(self.packet_path.parent),
            "--dangerously-skip-permissions",
        ]
        if self.model:
            cmd += ["--model", self.model]
        # Run from the packet's (scratch) dir so claude can't reach/clobber live state and doesn't
        # auto-load this repo's CLAUDE.md/skills (H3). Capture output; log it (debug) instead of flooding
        # the cron log; surface it only on non-zero exit, where it's the actionable diagnostic (H4).
        proc = subprocess.run(
            cmd,
            cwd=str(self.packet_path.parent),
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )
        log.debug("claude -p stdout: %s", (proc.stdout or "").strip()[:1000])
        if proc.returncode != 0:
            raise RuntimeError(
                f"`claude -p` failed (exit {proc.returncode}): {(proc.stderr or proc.stdout or '').strip()[:500]}"
            )


class ApiReasoner:
    """Provider-agnostic headless cloud pass. ``provider='anthropic'`` uses the Anthropic SDK with a
    forced tool call; ``provider='openai'`` uses any OpenAI-compatible endpoint (OpenRouter / Together /
    local vLLM) via ``base_url`` + a json-schema response. Same shared contract/schema as CodeReasoner,
    so it is drop-in equivalent. ``client`` is injected in tests."""

    def __init__(
        self,
        *,
        run_date: str,
        provider: str = "anthropic",
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        max_tokens: int = 8000,
        client=None,
    ) -> None:
        self.run_date = run_date
        self.provider = provider.strip().lower()
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.max_tokens = max_tokens
        self._client = client

    def reason(self, packet: ReasoningPacket) -> ModelOutput:
        if self.provider == "anthropic":
            data = self._anthropic(packet)
        elif self.provider in ("openai", "openrouter", "openai-compatible"):
            data = self._openai_compatible(packet)
        else:
            raise RuntimeError(
                f"ApiReasoner: unknown LLM_PROVIDER {self.provider!r} (use 'anthropic' or 'openai')"
            )
        return _parse_model_output(data, self.run_date)

    def _anthropic(self, packet: ReasoningPacket) -> dict[str, Any]:
        client = self._client
        if client is None:
            try:
                import anthropic
            except ImportError as exc:
                raise RuntimeError(
                    "ApiReasoner(anthropic) needs the 'api' extra: `uv sync --extra api`."
                ) from exc
            client = (
                anthropic.Anthropic(api_key=self.api_key)
                if self.api_key
                else anthropic.Anthropic()
            )
        tool = {
            "name": "emit_digest",
            "description": "Emit the daily digest ModelOutput for Avigail.",
            "input_schema": MODEL_OUTPUT_SCHEMA,
        }
        msg = client.messages.create(
            model=self.model or "claude-opus-4-8",
            max_tokens=self.max_tokens,
            system=_REASONER_SYSTEM,
            tools=[tool],
            tool_choice={"type": "tool", "name": "emit_digest"},
            messages=[
                {"role": "user", "content": json.dumps(packet, ensure_ascii=False)}
            ],
        )
        for block in msg.content:
            if (
                getattr(block, "type", None) == "tool_use"
                and block.name == "emit_digest"
            ):
                return dict(block.input)
        raise RuntimeError("ApiReasoner(anthropic): no emit_digest tool call returned")

    def _openai_compatible(self, packet: ReasoningPacket) -> dict[str, Any]:
        client = self._client
        if client is None:
            try:
                import openai
            except ImportError as exc:
                raise RuntimeError(
                    "ApiReasoner(openai) needs the 'api' extra: `uv sync --extra api`."
                ) from exc
            client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url)
        resp = client.chat.completions.create(
            model=self.model or "anthropic/claude-opus-4",
            max_tokens=self.max_tokens,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "model_output", "schema": MODEL_OUTPUT_SCHEMA},
            },
            messages=[
                {"role": "system", "content": _REASONER_SYSTEM},
                {"role": "user", "content": json.dumps(packet, ensure_ascii=False)},
            ],
        )
        content = resp.choices[0].message.content
        if not content:  # a tool-call/refusal/empty completion yields None — fail clearly, don't crash
            raise RuntimeError(
                "ApiReasoner(openai): empty response content (refusal or tool-call?) — no JSON to parse"
            )
        return json.loads(content)


def select_reasoner(
    env: Mapping[str, str],
    *,
    work_dir: str | Path,
    run_date: str,
    replay_path: str | Path | None = None,
) -> Reasoner:
    # `session` is the safe built-in default (never auto-shell-out / hit the network unless asked);
    # the deployed config selects `code` via .env. (H5: note + .env.example say so explicitly.)
    mode = env.get("REASONER", "session").strip().lower()
    work_dir = Path(work_dir)
    packet_path = work_dir / "packet.json"
    output_path = work_dir / "model_output.json"
    if mode == "replay":
        path = replay_path or env.get("REPLAY_OUTPUT") or output_path
        return ReplayReasoner(path)
    if mode == "code":
        # H3: hand the headless pass a dedicated scratch dir (packet + output ONLY). claude runs with
        # cwd + --add-dir scoped to it, so it can't reach live state (projects.json, watermarks) and
        # doesn't auto-load this repo's CLAUDE.md/skills.
        scratch = work_dir / ".reasoner"
        return CodeReasoner(
            packet_path=scratch / "packet.json",
            output_path=scratch / "model_output.json",
            run_date=run_date,
            claude_bin=env.get("CLAUDE_BIN", "claude"),
            model=env.get("CLAUDE_MODEL") or None,
        )
    if mode == "api":
        provider = env.get("LLM_PROVIDER", "anthropic").strip().lower()
        # H1: only fall back to ANTHROPIC_API_KEY for the Anthropic provider — NEVER hand it to a
        # third-party (OpenRouter/etc.) endpoint. openai-compatible requires its own LLM_API_KEY.
        api_key = env.get("LLM_API_KEY")
        if not api_key and provider == "anthropic":
            api_key = env.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                f"REASONER=api provider={provider!r} requires LLM_API_KEY"
                + (" or ANTHROPIC_API_KEY" if provider == "anthropic" else "")
            )
        return ApiReasoner(
            run_date=run_date,
            provider=provider,
            model=env.get("LLM_MODEL") or None,
            api_key=api_key,
            base_url=env.get("LLM_BASE_URL") or None,
        )
    return SessionReasoner(
        packet_path=packet_path, output_path=output_path, run_date=run_date
    )
