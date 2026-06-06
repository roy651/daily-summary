"""Digest window selection — prescribed (--since / --window-days) vs auto (min 2 days, extend to
the oldest watermark). The model never reasons about the window; this does."""

import types
from datetime import datetime, timezone

from mail_evidence import commit_watermark

from digest_core.cli import _digest_window_since


def _args(since=None, window_days=None):
    return types.SimpleNamespace(since=since, window_days=window_days)


def test_explicit_since_wins(tmp_path):
    assert (
        _digest_window_since(_args(since="2026-01-01"), tmp_path, "2026-06-06")
        == "2026-01-01"
    )


def test_window_days_prescribed(tmp_path):
    assert (
        _digest_window_since(_args(window_days=5), tmp_path, "2026-06-06")
        == "2026-06-01"
    )


def test_auto_floor_when_no_watermark(tmp_path, monkeypatch):
    monkeypatch.delenv("IMAP_ACCOUNTS", raising=False)
    monkeypatch.delenv("IMAP_HOST", raising=False)
    # nothing to extend to -> the 2-day minimum
    assert _digest_window_since(_args(), tmp_path, "2026-06-06") == "2026-06-04"


def test_auto_extends_back_to_watermark(tmp_path, monkeypatch):
    monkeypatch.setenv("IMAP_ACCOUNTS", "ula")
    monkeypatch.setenv("IMAP_ULA_HOST", "h")
    monkeypatch.setenv("IMAP_ULA_USER", "u")
    monkeypatch.setenv("IMAP_ULA_APP_PASSWORD", "p")
    commit_watermark(
        datetime(2026, 6, 3, 23, 59, 59, tzinfo=timezone.utc), tmp_path, name="ula"
    )
    # watermark 06-03 is older than the 2-day floor (06-04) -> window extends back to 06-03
    assert _digest_window_since(_args(), tmp_path, "2026-06-06") == "2026-06-03"
