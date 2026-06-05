"""Daily orchestration — the deterministic spine around the MODEL PASS (docs/02-pipeline.md).

``run_digest`` takes already-conditioned threads (so it is testable offline and source-agnostic) and
runs: unify -> packet -> MODEL PASS -> apply -> render -> deliver -> persist. The CLI wires the mail
pull + watermark around it; the watermark is committed only after delivery succeeds.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from mail_evidence.records import Thread

from digest_core.apply import apply_model_output
from digest_core.contacts import DigestContactStore
from digest_core.delivery import DeliveryResult
from digest_core.evidence import unify
from digest_core.packet import build_reasoning_packet
from digest_core.reasoner import Reasoner, ReasoningPacket
from digest_core.render import render_digest_md, render_todos_md
from digest_core.schema import ModelOutput
from digest_core.state import ClientProfile, Project, write_clients, write_projects
from digest_core.todos import prioritize


@dataclass
class DigestResult:
    run_date: str
    projects: list[Project]
    output: ModelOutput
    delivery: DeliveryResult
    packet: ReasoningPacket


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
    persist: bool = True,
) -> DigestResult:
    cleaned = unify(threads, self_addresses=self_addresses)
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
    )
    output = reasoner.reason(packet)  # may raise SessionPending (caught by the CLI)
    projects = apply_model_output(
        projects, output, run_date=run_date, thread_dates=thread_dates
    )

    digest_md = render_digest_md(output, projects, run_date=run_date)
    todos_md = render_todos_md(
        prioritize(projects, run_date=run_date), run_date=run_date
    )
    result = delivery.deliver(digest_md, todos_md, run_date=run_date)

    if persist:
        state_dir = Path(state_dir)
        write_projects(projects, state_dir / "projects.json")
        write_clients(clients, state_dir / "clients.json")
        contacts.save(state_dir / "contacts.json")

    return DigestResult(
        run_date=run_date,
        projects=projects,
        output=output,
        delivery=result,
        packet=packet,
    )
