"""Daily orchestration — the deterministic spine around the MODEL PASS (docs/02-pipeline.md).

``run_digest`` takes already-conditioned threads (so it is testable offline and source-agnostic) and
runs: unify -> packet -> MODEL PASS -> apply -> render -> deliver -> persist. The CLI wires the mail
pull + watermark around it; the watermark is committed only after delivery succeeds.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from mail_evidence.records import Thread

from digest_core.apply import (
    apply_corrections,
    apply_insights,
    apply_model_output,
    promote_work_contacts,
    upsert_clients,
)
from digest_core.billing import apply_billing_signals
from digest_core.contacts import DigestContactStore
from digest_core.delivery import DeliveryResult
from digest_core.evidence import unify
from digest_core.knowledge import KnowledgeStore
from digest_core.packet import build_reasoning_packet
from digest_core.reasoner import Reasoner, ReasoningPacket
from digest_core.relevance import partition_marketing
from digest_core.render import (
    render_digest_md,
    render_state_review_md,
    render_todos_md,
)
from digest_core.schema import ModelOutput
from digest_core.state import ClientProfile, Project, write_clients, write_projects
from digest_core.todos import (
    auto_archive_billed,
    close_todos_from_feedback,
    prioritize,
    suspected_closures,
)


@dataclass
class DigestResult:
    run_date: str
    projects: list[Project]
    clients: list[ClientProfile]
    output: ModelOutput
    delivery: DeliveryResult
    packet: ReasoningPacket
    filtered: list[
        Thread
    ]  # threads demoted as bulk/marketing this run (surfaced, not silently dropped)
    closed_from_feedback: int = 0  # todos cleared from Avigail's check-offs this run
    suspected: list = field(
        default_factory=list
    )  # decay guesses surfaced for confirmation


def thread_max_dates(threads: list[Thread]) -> dict[str, str]:
    """Map each thread to the latest evidence date it carries (observed-truth for last_activity)."""
    return {
        t.thread_id: max(r.date.date().isoformat() for r in t.records)
        for t in threads
        if t.records
    }


def run_digest(
    *,
    projects: list[Project],
    clients: list[ClientProfile],
    contacts: DigestContactStore,
    threads: list[Thread],
    reasoner: Reasoner,
    delivery,
    run_date: str,
    since: str,
    self_addresses: Iterable[str],
    state_dir: str | Path,
    out_dir: str | Path,
    knowledge: KnowledgeStore | None = None,
    persist: bool = True,
) -> DigestResult:
    knowledge = knowledge if knowledge is not None else KnowledgeStore()

    # Threads Avigail has flagged off (persisted): never surface them again, this run or later.
    suppressed_path = Path(state_dir) / "suppressed.json"
    suppressed: set[str] = (
        set(json.loads(suppressed_path.read_text(encoding="utf-8")))
        if suppressed_path.exists()
        else set()
    )

    # CLOSE first (the "remove" half): consume Avigail's check-offs from the previous run's todos file
    # (or email reply) and clear those todos before composing today's digest. Highest-confidence closure.
    closed_from_feedback = 0
    # File backend reads out/todos.md; email backend scans the just-pulled threads for Avigail's reply.
    feedback = delivery.collect_feedback(run_date=run_date, threads=threads)
    if feedback:
        if feedback.eod_actuals:
            closed_from_feedback = close_todos_from_feedback(
                projects, feedback.eod_actuals
            )
        # Human-triggered project closure/revival (the other dormancy trigger). Soft archive: a later
        # new item revives it (apply flips status back), so we don't lock status_confirmed here.
        by_id = {p.project_id: p for p in projects}
        for pid in feedback.archived_projects:
            if pid in by_id:
                by_id[pid].status = "archived"
        for pid in feedback.revived_projects:
            if pid in by_id:
                by_id[pid].status = "active"
                by_id[pid].billed_on = None
        # Route Avigail's free-text corrections into the knowledge store (provenance = feedback), so they
        # reach the reasoner via the next packet and outrank its guesses — e.g. an entity fix like
        # "Rock Design is just Idan's studio, my web dev — not a separate vendor".
        if feedback.freeform_notes.strip():
            knowledge.add_general(
                feedback.freeform_notes.strip(), date=run_date, source="feedback"
            )
        suppressed.update(feedback.suppressed_threads)
        # Apply Avigail's explicit corrections (retract false knowledge / merge contacts) BEFORE the
        # packet, so the reasoner sees the corrected world this run. Feedback outranks the model.
        apply_corrections(
            feedback.corrections,
            knowledge,
            contacts,
            run_date=run_date,
            source="feedback",
        )

    cleaned = unify(threads, self_addresses=self_addresses)
    # N2: demote clear bulk/marketing so the model isn't buried in noise — but surface what we dropped.
    cleaned, filtered = partition_marketing(cleaned)
    # Drop suppressed threads entirely — Avigail flagged them off, so the reasoner never sees them.
    if suppressed:
        cleaned = [t for t in cleaned if t.thread_id not in suppressed]
    # C2: billing direction is the cleanest role signal — set counterparty roles (outbound invoice ->
    # client, inbound -> subcontractor) before the packet, so the reasoner reasons over correct roles.
    apply_billing_signals(
        cleaned, contacts, knowledge, self_addresses, run_date=run_date
    )
    thread_dates = thread_max_dates(cleaned)

    packet = build_reasoning_packet(
        run_date=run_date,
        since=since,
        until=run_date,
        projects=projects,
        clients=clients,
        contacts=contacts,
        threads=cleaned,
        self_addresses=self_addresses,
        knowledge_general=knowledge.general_notes(mark_confirmed=True),
    )
    output = reasoner.reason(packet)  # may raise SessionPending (caught by the CLI)
    projects = apply_model_output(
        projects, output, run_date=run_date, thread_dates=thread_dates
    )
    # K3: ensure clients discovered this run have a profile; then promote the work contacts the model
    # attached to real work (the reasoning test) and route tacit-knowledge insights.
    clients = upsert_clients(projects, clients)
    promote_work_contacts(projects, clients, contacts, run_date=run_date)
    apply_insights(output, clients, knowledge, run_date=run_date)
    # The reasoner's own reconciliations (e.g. it noticed two addresses are one person and retracts the
    # stale "distinct" note + merges the contacts). Model-sourced: won't override a human-set role.
    apply_corrections(
        output.corrections, knowledge, contacts, run_date=run_date, source="model"
    )

    # Evidence-based reversible closure: fully-billed + silent projects auto-archive (billed this run
    # had its activity floored to run_date, so it won't archive until silence actually accrues).
    auto_archive_billed(projects, run_date=run_date)

    # DECAY pass: surface (don't delete) projects/todos that look finished or dormant, for confirmation.
    suspected = suspected_closures(projects, run_date=run_date)

    digest_md = render_digest_md(
        output, projects, run_date=run_date, filtered=filtered, suspected=suspected
    )
    todos_md = render_todos_md(
        prioritize(projects, run_date=run_date), run_date=run_date
    )
    # Always write the readable artifacts to out/ — they're the canonical output and the editable
    # feedback surface, so a `--dry-run` (which sends/persists nothing) still leaves them to inspect.
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"digest_{run_date}.md").write_text(digest_md, encoding="utf-8")
    (out_dir / "todos.md").write_text(todos_md, encoding="utf-8")
    # Refresh the human-readable state map every run, so the audit surface (clients/projects/contacts &
    # roles) is never stale. `digest review` regenerates the same on demand without a model pass.
    (out_dir / "state-review.md").write_text(
        render_state_review_md(clients, projects, contacts), encoding="utf-8"
    )
    # Delivery is the SEND step (email backend, unless dry); the file backend is a no-op given the above.
    result = delivery.deliver(digest_md, todos_md, run_date=run_date)

    if persist:
        state_dir = Path(state_dir)
        write_projects(projects, state_dir / "projects.json")
        write_clients(clients, state_dir / "clients.json")
        contacts.save(state_dir / "contacts.json")
        knowledge.save(state_dir / "knowledge.json")
        if suppressed:
            suppressed_path.write_text(
                json.dumps(sorted(suppressed), indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

    return DigestResult(
        run_date=run_date,
        projects=projects,
        clients=clients,
        output=output,
        delivery=result,
        packet=packet,
        filtered=filtered,
        closed_from_feedback=closed_from_feedback,
        suspected=suspected,
    )
