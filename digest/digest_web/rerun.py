"""On-demand 'Re-run digest' for the dashboard (docs/08 'Run now'). Refresh semantics: pull + reason
+ persist state + write the digest, but DON'T email and DON'T advance the watermark — i.e. the CLI's
`daily --no-send`. The model call takes a minute or two, so it runs in a background thread: the button
swaps to a spinner that polls until done, then reloads the page to show the fresh digest. Single-user,
so one run at a time guarded by a lock; nothing here writes client-facing output."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from digest_web import service

router = APIRouter(prefix="/actions")
_REPO = (
    Path(__file__).resolve().parents[2]
)  # repo root: .../digest_web -> digest -> repo

_lock = threading.Lock()
_state: dict = {"running": False, "ok": None, "error": ""}


def _invoke_cli() -> tuple[bool, str]:
    """Run `daily --no-send` as a subprocess (same venv python, .env loaded by the CLI). Returns
    (ok, error_tail). Replaceable in tests so the state machine can be exercised without a model call."""
    env = dict(os.environ)
    # Make uv/claude/node resolvable even under a minimal systemd PATH (claude is found via CLAUDE_BIN
    # in .env, but it may itself shell out): prepend the venv bin and the user-local bin.
    env["PATH"] = (
        f"{Path(sys.executable).parent}:{Path.home() / '.local/bin'}:"
        + env.get("PATH", "")
    )
    cmd = [
        sys.executable,
        "-m",
        "digest_core.cli",
        "daily",
        "--no-send",
        "--state-dir",
        str(service.state_dir().resolve()),
        "--out-dir",
        str(service.out_dir().resolve()),
    ]
    try:
        proc = subprocess.run(
            cmd, cwd=str(_REPO), capture_output=True, text=True, timeout=1200, env=env
        )
        ok = proc.returncode == 0
        return ok, "" if ok else (proc.stderr or proc.stdout or "").strip()[-400:]
    except (
        Exception
    ) as exc:  # timeout / spawn failure — surface it, don't hang the button
        return False, str(exc)[-400:]


def _worker() -> None:
    ok, err = _invoke_cli()
    with _lock:
        _state.update(running=False, ok=ok, error=err)


def _start() -> None:  # seam: tests replace this to run synchronously
    threading.Thread(target=_worker, daemon=True).start()


def _spinner() -> HTMLResponse:
    """A self-polling placeholder: re-checks status every 2s until the run finishes."""
    return HTMLResponse(
        '<span id="rerun" class="muted" hx-get="/actions/run-now/status" '
        'hx-trigger="every 2s" hx-swap="outerHTML">⏳ Re-running… (~1–2 min)</span>'
    )


def _button(note: str = "", err: bool = False) -> HTMLResponse:
    extra = (
        f' <span class="muted" style="color:{"#b3261e" if err else "inherit"}">{note}</span>'
        if note
        else ""
    )
    return HTMLResponse(
        '<button id="rerun" hx-post="/actions/run-now" hx-target="#rerun" '
        f'hx-swap="outerHTML">🔄 Re-run digest</button>{extra}'
    )


@router.post("/run-now", response_class=HTMLResponse)
def run_now() -> HTMLResponse:
    with _lock:
        already = _state["running"]
        if not already:
            _state.update(running=True, ok=None, error="")
    if not already:
        _start()
    return _spinner()


@router.get("/run-now/status", response_class=HTMLResponse)
def run_now_status() -> HTMLResponse:
    with _lock:
        running, ok, err = _state["running"], _state["ok"], _state["error"]
    if running:
        return _spinner()
    if ok:
        return HTMLResponse(
            "", headers={"HX-Refresh": "true"}
        )  # reload → fresh digest + last-run
    return _button("⚠ run failed — see state/cron logs" if err else "", err=bool(err))
