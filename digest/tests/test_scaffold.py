"""Phase-0 scaffold smoke tests.

Confirms (a) the daily-summary package imports and (b) the shared mail-evidence engine is wired in
and reachable through its public API. These are the Phase-0 acceptance gate; they are replaced by
real behavioral tests as Phase 1 lands.
"""


def test_digest_core_imports():
    import digest_core

    assert digest_core.__version__


def test_mail_evidence_public_api_reachable():
    # The shared input layer must be importable via its editable install.
    from mail_evidence import ingest_email_export, run

    assert callable(ingest_email_export)
    assert callable(run)
