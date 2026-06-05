"""build_reasoning_packet() — the pure-data MODEL PASS input (docs/05-model-seam.md).

Asserts the packet's shape and JSON-serializability. No formatting lives here (that's render.py);
the packet is what gets written to packet.json for the model.
"""

import json
from datetime import datetime, timezone

from mail_evidence import Thread
from mail_evidence.records import AttachmentMeta, EvidenceRecord

from digest_core.contacts import DigestContactStore
from digest_core.packet import build_reasoning_packet
from digest_core.state import ClientProfile, ManagingContact, Project, Todo

SELF = {"avigail@ula.example"}


def _thread():
    return Thread(
        thread_id="t-1",
        tier="T1",
        records=[
            EvidenceRecord(
                id="m1",
                thread_id="t-1",
                source="email",
                date=datetime(2026, 6, 5, 9, 0, tzinfo=timezone.utc),
                body_text="Can you send v2?",
                from_="agent@sprig.example",
                to=["avigail@ula.example"],
                cc=["dana@example.com"],
                subject="Homepage v2",
                attachments_meta=[AttachmentMeta("brief.pdf", "application/pdf", 1234)],
            )
        ],
    )


def _state():
    projects = [
        Project(
            project_id="p1",
            client_id="sprig",
            end_client="rhythmedix",
            title="Website",
            status="active",
            assignee="self",
            open_todos=[
                Todo(
                    "send v2",
                    "communicate_client",
                    "agent@sprig.example",
                    None,
                    "asked",
                    "t-1",
                )
            ],
            evidence_thread_ids=["t-1"],
        )
    ]
    clients = [
        ClientProfile(
            client_id="sprig",
            display_name="SPRIG",
            is_agency=True,
            managing_contacts=[ManagingContact("Avi", "agent@sprig.example")],
        )
    ]
    contacts = DigestContactStore()
    contacts.add("agent@sprig.example", role="agent", source="bootstrap")
    return projects, clients, contacts


def test_packet_shape_and_serializable():
    projects, clients, contacts = _state()
    packet = build_reasoning_packet(
        run_date="2026-06-05",
        since="2026-06-04",
        until="2026-06-05",
        projects=projects,
        clients=clients,
        contacts=contacts,
        threads=[_thread()],
        self_addresses=SELF,
    )

    # top-level keys
    assert set(packet) >= {
        "run_date",
        "window",
        "current_projects",
        "clients",
        "contacts",
        "threads",
        "glossary",
    }
    assert packet["window"] == {"since": "2026-06-04", "until": "2026-06-05"}

    # projects carry the running state the model updates
    proj = packet["current_projects"][0]
    assert proj["project_id"] == "p1"
    assert proj["end_client"] == "rhythmedix"
    assert proj["open_todos"][0]["category"] == "communicate_client"

    # contacts let the model tell an agent from a sub
    assert {"email": "agent@sprig.example", "role": "agent"} in packet["contacts"]

    # threads carry evidence with direction + attachment names
    rec = packet["threads"][0]["records"][0]
    assert rec["direction"] == "inbound"
    assert rec["attachments"] == ["brief.pdf"]
    assert rec["subject"] == "Homepage v2"

    # the whole thing is JSON-serializable (it gets written to packet.json)
    assert json.loads(json.dumps(packet))


def test_packet_glossary_mentions_agency_nuance():
    projects, clients, contacts = _state()
    packet = build_reasoning_packet(
        run_date="2026-06-05",
        since="2026-06-04",
        until="2026-06-05",
        projects=projects,
        clients=clients,
        contacts=contacts,
        threads=[],
        self_addresses=SELF,
    )
    assert "agency" in packet["glossary"].lower()
