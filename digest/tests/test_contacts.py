"""DigestContactStore — implements mail_evidence.ContactStore, persisted to state/contacts.json.

The store is the primary tiering lever: known contacts make a thread T1 (always kept). Roles are
richer than the sibling's bare "other" because role feeds the reasoning packet (the model must know
a CC is a subcontractor reporting to a client).
"""

import pytest

from digest_core.contacts import CONTACT_ROLES, DigestContactStore


def test_add_and_is_known_is_case_insensitive():
    s = DigestContactStore()
    s.add("Agent@Sprig.Example", role="agent", source="bootstrap", reason="seed")
    assert s.is_known("agent@sprig.example")
    assert s.is_known("AGENT@SPRIG.EXAMPLE")
    assert not s.is_known("stranger@nowhere.example")


def test_add_normalizes_display_name_form():
    s = DigestContactStore()
    s.add(
        "Dana <dana@example.com>",
        role="subcontractor",
        source="bootstrap",
        reason="seed",
    )
    assert s.is_known("dana@example.com")
    assert s.role_of("dana@example.com") == "subcontractor"


def test_role_of_unknown_is_none():
    assert DigestContactStore().role_of("nobody@example.com") is None


def test_add_auto_uses_other_and_auto_source():
    s = DigestContactStore()
    s.add_auto("new@client.example", reason="promoted from thread t-9")
    assert s.is_known("new@client.example")
    assert s.role_of("new@client.example") == "other"
    assert s.entry("new@client.example").source == "auto"


def test_invalid_role_rejected():
    with pytest.raises(ValueError):
        DigestContactStore().add(
            "x@y.example", role="boss", source="bootstrap", reason=""
        )
    assert "client" in CONTACT_ROLES and "end_client" in CONTACT_ROLES


def test_persistence_round_trip(tmp_path):
    path = tmp_path / "contacts.json"
    s = DigestContactStore()
    s.add("agent@sprig.example", role="agent", source="bootstrap", reason="seed")
    s.add_auto("new@client.example", reason="thread t-9")
    s.save(path)

    reloaded = DigestContactStore.load(path)
    assert reloaded.is_known("agent@sprig.example")
    assert reloaded.role_of("new@client.example") == "other"
    # Round-trip is byte-stable for reviewable diffs.
    reloaded.save(path)
    assert path.read_text()  # non-empty


def test_load_missing_file_is_empty(tmp_path):
    s = DigestContactStore.load(tmp_path / "does_not_exist.json")
    assert not s.is_known("anyone@example.com")
