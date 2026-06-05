"""Review-2 pre-backfill fixes: reasoning-based contact promotion (N1/N3), client upsert (K3),
conservative marketing denoise (N2), and the R1 assert->raise guard.
"""

from datetime import datetime, timezone

from mail_evidence import Thread
from mail_evidence.records import EvidenceRecord

from digest_core.apply import (
    apply_model_output,
    promote_work_contacts,
    upsert_clients,
)
from digest_core.contacts import DigestContactStore
from digest_core.relevance import looks_like_marketing, partition_marketing
from digest_core.schema import ModelOutput
from digest_core.state import ClientProfile, Project


# ── N1/N3: reasoning-based contact promotion ──


def _promote(output_dict):
    contacts = DigestContactStore()
    promote_work_contacts(
        ModelOutput.from_dict(output_dict), contacts, run_date="2026-05-15"
    )
    return contacts


def test_subcontractor_and_targets_promoted_with_roles():
    c = _promote(
        {
            "project_updates": [
                {
                    "project_id": None,
                    "client_id": "sprig",
                    "end_client": "rhythmedix",
                    "title": "Booth",
                    "subcontractor": "dana@x.example",
                    "todos": [
                        {
                            "text": "ask agent",
                            "category": "communicate_client",
                            "target": "molly@sprig.example",
                        },
                        {
                            "text": "check sub",
                            "category": "verify_subcontractor",
                            "target": "idan@x.example",
                        },
                        {"text": "do it myself", "category": "self", "target": None},
                    ],
                }
            ]
        }
    )
    assert c.role_of("dana@x.example") == "subcontractor"
    assert (
        c.role_of("molly@sprig.example") == "agent"
    )  # communicate_client on agency work (end_client set)
    assert c.role_of("idan@x.example") == "subcontractor"


def test_communicate_target_on_direct_client_is_client_not_agent():
    c = _promote(
        {
            "project_updates": [
                {
                    "project_id": None,
                    "client_id": "hospitech",
                    "title": "Flyer",
                    "todos": [
                        {
                            "text": "ask",
                            "category": "communicate_client",
                            "target": "tzipi@hospitech.example",
                        }
                    ],
                }
            ]
        }
    )
    assert (
        c.role_of("tzipi@hospitech.example") == "client"
    )  # no end_client -> direct -> client


def test_non_email_target_and_unrelated_addresses_not_promoted():
    c = _promote(
        {
            "project_updates": [
                {
                    "project_id": "p1",
                    "todos": [
                        {
                            "text": "x",
                            "category": "communicate_client",
                            "target": "the client",
                        }
                    ],
                }
            ]
        }
    )
    assert c.items() == []  # "the client" isn't an email; nothing promoted


def test_inferred_role_does_not_flip_established_role():
    c = DigestContactStore()
    c.add("molly@sprig.example", role="agent", source="bootstrap")
    # A later model promotion as "client" must NOT overwrite the established "agent".
    promote_work_contacts(
        ModelOutput.from_dict(
            {
                "project_updates": [
                    {
                        "project_id": "p1",
                        "todos": [
                            {
                                "text": "x",
                                "category": "communicate_client",
                                "target": "molly@sprig.example",
                            }
                        ],
                    }
                ]
            }
        ),
        c,
        run_date="2026-05-15",
    )
    assert c.role_of("molly@sprig.example") == "agent"


# ── K3: client upsert ──


def test_upsert_creates_missing_preserves_existing():
    existing = [
        ClientProfile(
            client_id="sprig", display_name="SPRIG Consulting", is_agency=True
        )
    ]
    projects = [
        Project(project_id="p1", client_id="sprig", title="A", status="active"),
        Project(project_id="p2", client_id="newco", title="B", status="active"),
    ]
    clients = upsert_clients(projects, existing)
    by_id = {c.client_id: c for c in clients}
    assert by_id["sprig"].is_agency is True  # untouched
    assert by_id["sprig"].display_name == "SPRIG Consulting"
    assert "newco" in by_id and by_id["newco"].display_name == "Newco"  # stub created


# ── N2: conservative marketing denoise ──


def _rec(from_, subject="hi", bulk=False):
    return EvidenceRecord(
        id="m",
        thread_id="t",
        source="email",
        date=datetime(2026, 5, 15, tzinfo=timezone.utc),
        body_text="b",
        from_=from_,
        subject=subject,
        is_bulk=bulk,
    )


def test_marketing_detected_by_structure_only():
    assert looks_like_marketing(_rec("no-reply@bank.example"))
    assert looks_like_marketing(_rec("promo@hub.flashyapp.com"))
    assert looks_like_marketing(_rec("anyone@x.example", bulk=True))
    # A real human client is NOT marketing, even with Hebrew content / a 'newsletter-ish' subject.
    assert not looks_like_marketing(
        _rec("molly@sprigconsulting.com", subject="עדכון על הפרויקט")
    )
    assert not looks_like_marketing(_rec("tzipi@hospitech.co.il"))


def test_partition_drops_all_marketing_threads_keeps_mixed():
    pure = Thread(
        thread_id="t1",
        tier="T2",
        records=[_rec("no-reply@x.example"), _rec("news@flashy.app")],
    )
    mixed = Thread(
        thread_id="t2",
        tier="T2",
        records=[_rec("no-reply@x.example"), _rec("molly@sprigconsulting.com")],
    )
    kept, dropped = partition_marketing([pure, mixed])
    assert [t.thread_id for t in dropped] == ["t1"]
    assert [t.thread_id for t in kept] == ["t2"]  # one human reply keeps the thread


# ── R1: confirmed-column guard is a runtime raise (survives python -O), not an assert ──


def test_confirmed_guard_is_a_runtime_raise():
    import inspect

    import digest_core.apply as apply_mod

    # The guard must be an explicit raise, not an `assert` (which `python -O` strips) — R1.
    src = inspect.getsource(apply_mod.apply_model_output)
    assert "raise RuntimeError" in src
    assert "assert " not in src

    # And normal apply preserves a pre-set confirmed value (never writes it).
    projs = [
        Project(
            project_id="p1",
            client_id="c",
            title="t",
            status="active",
            status_confirmed="on_hold",
        )
    ]
    out = ModelOutput.from_dict(
        {"project_updates": [{"project_id": "p1", "status_agent": "active"}]}
    )
    assert (
        apply_model_output(projs, out, run_date="2026-05-15")[0].status_confirmed
        == "on_hold"
    )
