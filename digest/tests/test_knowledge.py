"""Tacit-knowledge capture layer (docs/01 learning layer).

The model can emit project observations, client observations, and general insights; these persist
and are fed back into the next packet. This is the capture+storage half of learning (feedback
consumption stays phase 2).
"""

from digest_core.apply import apply_insights, apply_model_output
from digest_core.knowledge import KnowledgeStore
from digest_core.schema import ModelOutput
from digest_core.state import ClientProfile, Project


def test_knowledge_store_dedups_and_round_trips(tmp_path):
    k = KnowledgeStore()
    k.add_general("SPRIG works US hours", date="2026-03-01")
    k.add_general("SPRIG works US hours", date="2026-04-01")  # dup -> ignored
    k.add_general("Nurit is the main design partner", date="2026-03-01")
    assert len(k.general) == 2
    path = tmp_path / "knowledge.json"
    k.save(path)
    assert sorted(KnowledgeStore.load(path).general_notes()) == sorted(
        ["SPRIG works US hours", "Nurit is the main design partner"]
    )


def test_project_observations_accumulate():
    projects = [Project(project_id="p1", client_id="sprig", title="X", status="active")]
    out = ModelOutput.from_dict(
        {
            "project_updates": [
                {
                    "project_id": "p1",
                    "status_agent": "active",
                    "observations": ["client prefers blue", "tight timeline"],
                }
            ]
        }
    )
    projects = apply_model_output(projects, out, run_date="2026-03-01")
    notes = [o.note for o in projects[0].observations]
    assert "client prefers blue" in notes and "tight timeline" in notes
    # Re-applying the same note doesn't duplicate it.
    projects = apply_model_output(
        projects,
        ModelOutput.from_dict(
            {
                "project_updates": [
                    {
                        "project_id": "p1",
                        "status_agent": "active",
                        "observations": ["client prefers blue"],
                    }
                ]
            }
        ),
        run_date="2026-04-01",
    )
    assert [o.note for o in projects[0].observations].count("client prefers blue") == 1


def test_insights_route_to_general_and_client():
    clients = [ClientProfile(client_id="sprig", display_name="SPRIG", is_agency=True)]
    knowledge = KnowledgeStore()
    out = ModelOutput.from_dict(
        {
            "insights": [
                {
                    "scope": "general",
                    "note": "Avigail's weekend is Fri-Sat (offset from US clients)",
                },
                {"scope": "sprig", "note": "Weekly Molly sync on Thursdays"},
                {"scope": "unknown_client", "note": "falls back to general"},
            ]
        }
    )
    apply_insights(out, clients, knowledge, run_date="2026-03-01")
    assert (
        "Avigail's weekend is Fri-Sat (offset from US clients)"
        in knowledge.general_notes()
    )
    assert (
        "falls back to general" in knowledge.general_notes()
    )  # unknown scope -> general, never dropped
    assert any(
        o.note == "Weekly Molly sync on Thursdays" for o in clients[0].observations
    )
