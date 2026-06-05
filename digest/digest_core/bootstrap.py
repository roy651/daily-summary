"""Cold-start bootstrap — build the initial client/project map (docs/02-pipeline.md).

Reads a batch of already-fetched records (the sibling's export, once), holds out the most recent
week for ground-truth collection, conditions the rest, seeds the contact store, and runs a MODEL
PASS to propose the opening project map. Best-effort by design: expect to hand-correct the result.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from email.utils import parseaddr

from mail_evidence.records import EvidenceRecord, Thread

from digest_core.apply import apply_model_output
from digest_core.contacts import DigestContactStore
from digest_core.evidence import condition_records
from digest_core.packet import build_reasoning_packet
from digest_core.reasoner import Reasoner
from digest_core.relevance import KeepAllHumanJudge
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


def _human_addresses(record: EvidenceRecord, self_addresses: set[str]) -> list[str]:
    if record.source != "email":
        return []
    raw = [record.from_, *record.to, *record.cc]
    out = []
    for r in raw:
        if not r:
            continue
        addr = (parseaddr(r)[1] or r).strip().lower()
        if addr and addr not in self_addresses:
            out.append(addr)
    return out


def _seed_contacts(
    threads: list[Thread], contacts: DigestContactStore, self_addresses: set[str]
) -> None:
    # Roles are seeded as "other"; the model's packet + manual review refine them later. (Richer
    # role inference is a deliberate phase-2 nicety, not an MVP blocker.)
    for t in threads:
        for r in t.records:
            for addr in _human_addresses(r, self_addresses):
                if not contacts.is_known(addr):
                    contacts.add(addr, role="other", source="bootstrap")


def _derive_clients(
    projects: list[Project], existing: list[ClientProfile] | None = None
) -> list[ClientProfile]:
    known = {c.client_id: c for c in (existing or [])}
    for p in projects:
        if p.client_id and p.client_id not in known:
            known[p.client_id] = ClientProfile(
                client_id=p.client_id,
                display_name=p.client_id.replace("-", " ").replace("_", " ").title(),
            )
    return [known[k] for k in sorted(known)]


def run_bootstrap(
    *,
    records: list[EvidenceRecord],
    reasoner: Reasoner,
    run_date: str,
    holdout_days: int,
    self_addresses: Iterable[str],
    contacts: DigestContactStore | None = None,
) -> BootstrapResult:
    self_addresses = {a.strip().lower() for a in self_addresses}
    cutoff = date.fromisoformat(run_date) - timedelta(days=holdout_days)
    kept = [r for r in records if r.date.date() < cutoff]

    contacts = contacts or DigestContactStore()
    threads = condition_records(kept, judge=KeepAllHumanJudge(), contact_store=contacts)
    _seed_contacts(threads, contacts, self_addresses)

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
    )
    output = reasoner.reason(packet)
    projects = apply_model_output([], output, run_date=run_date, thread_dates={})
    clients = _derive_clients(projects)
    return BootstrapResult(projects=projects, clients=clients, contacts=contacts)
