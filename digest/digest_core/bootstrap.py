"""Cold-start bootstrap — build the initial client/project map (docs/02-pipeline.md).

Reads a batch of already-fetched records (the sibling's export, once), holds out the most recent
week for ground-truth collection, conditions the rest, and runs a MODEL PASS to propose the opening
project map. Contacts are then promoted from what the model tied to real work (not indiscriminate
seeding). Best-effort by design: expect to hand-correct the result.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from mail_evidence.records import EvidenceRecord

from digest_core.apply import (
    apply_insights,
    apply_model_output,
    promote_work_contacts,
    upsert_clients,
)
from digest_core.contacts import DigestContactStore
from digest_core.evidence import condition_records
from digest_core.knowledge import KnowledgeStore
from digest_core.packet import build_reasoning_packet
from digest_core.reasoner import Reasoner
from digest_core.relevance import KeepAllHumanJudge, partition_marketing
from digest_core.state import ClientProfile, Project

BOOTSTRAP_GLOSSARY = (
    "COLD START. You are building Avigail's initial project map from a backlog of email. Group the "
    "threads into ongoing projects (project_id=null for each one you discover; include client_id and "
    "title). Infer each project's current status, owner, blockers, and any deadline. SPRIG is an "
    "agency with end-clients; subcontractors sometimes deal with clients directly and CC Avigail."
)


@dataclass
class BootstrapResult:
    projects: list[Project]
    clients: list[ClientProfile]
    contacts: DigestContactStore
    knowledge: KnowledgeStore


def run_bootstrap(
    *,
    records: list[EvidenceRecord],
    reasoner: Reasoner,
    run_date: str,
    holdout_days: int,
    self_addresses: Iterable[str],
    contacts: DigestContactStore | None = None,
    knowledge: KnowledgeStore | None = None,
    since: str | None = None,
) -> BootstrapResult:
    knowledge = knowledge if knowledge is not None else KnowledgeStore()
    self_addresses = {a.strip().lower() for a in self_addresses}
    cutoff = date.fromisoformat(run_date) - timedelta(days=holdout_days)
    lo = date.fromisoformat(since) if since else None
    kept = [
        r
        for r in records
        if r.date.date() < cutoff and (lo is None or r.date.date() >= lo)
    ]

    contacts = contacts or DigestContactStore()
    threads = condition_records(kept, judge=KeepAllHumanJudge(), contact_store=contacts)
    # N2: same conservative bulk/marketing demotion as the daily path, so the cold-start packet isn't
    # buried in noise either. (Dropped threads can't become projects; not surfaced here as there's no digest.)
    threads, _filtered = partition_marketing(threads)

    since = min((r.date.date().isoformat() for r in kept), default=cutoff.isoformat())
    packet = build_reasoning_packet(
        run_date=run_date,
        since=since,
        until=cutoff.isoformat(),
        projects=[],
        clients=[],
        contacts=contacts,
        threads=threads,
        self_addresses=self_addresses,
        glossary=BOOTSTRAP_GLOSSARY,
        knowledge_general=knowledge.general_notes(),
    )
    output = reasoner.reason(packet)
    projects = apply_model_output([], output, run_date=run_date, thread_dates={})
    clients = upsert_clients(projects)
    # Reasoning-based contact promotion: only people the model tied to real work become known (+roles).
    promote_work_contacts(projects, clients, contacts, run_date=run_date)
    apply_insights(output, clients, knowledge, run_date=run_date)
    return BootstrapResult(
        projects=projects, clients=clients, contacts=contacts, knowledge=knowledge
    )
