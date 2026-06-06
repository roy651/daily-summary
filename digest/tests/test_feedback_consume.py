"""Feedback consume — Avigail's free-text corrections must land in the knowledge store (provenance
'feedback') so the reasoner sees them next run. This is how an entity fix like 'Rock Design is Idan'
sticks without her editing JSON."""

from digest_core.contacts import DigestContactStore
from digest_core.daily import run_digest
from digest_core.delivery import DeliveryResult
from digest_core.feedback import FeedbackRecord
from digest_core.knowledge import KnowledgeStore
from digest_core.schema import ModelOutput


class _StubDelivery:
    def collect_feedback(self, *, run_date):
        return FeedbackRecord(
            run_date=run_date,
            freeform_notes="Rock Design is just Idan's studio (my web dev) — not a separate vendor.",
        )

    def deliver(self, digest_md, todos_md, *, run_date):
        return DeliveryResult(backend="file", sent=True, detail="stub")


class _StubReasoner:
    def reason(self, packet):
        return ModelOutput.from_dict(
            {
                "project_updates": [],
                "digest_updates": [],
                "unresolved": [],
                "insights": [],
            }
        )


def test_freeform_feedback_note_lands_in_knowledge(tmp_path):
    knowledge = KnowledgeStore()
    run_digest(
        projects=[],
        clients=[],
        contacts=DigestContactStore.load(tmp_path / "contacts.json"),
        threads=[],
        reasoner=_StubReasoner(),
        delivery=_StubDelivery(),
        run_date="2026-06-06",
        since="2026-06-04",
        self_addresses=["avigail@ula.co.il"],
        state_dir=tmp_path,
        out_dir=tmp_path,
        knowledge=knowledge,
        persist=False,
    )
    assert any("Rock Design" in n for n in knowledge.general_notes())
