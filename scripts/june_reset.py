"""One-time "June reset" (throwaway maintenance, NOT a CLI command).

Avigail's open-todo list was bloated by months of items the system never closed (missing info). To
start her from a clean slate, archive every project with no activity since a cutoff (default
2026-06-01). Knowledge is untouched. Archived projects' todos stop surfacing because the packet,
prioritizer, and renderer all skip archived/done projects — and it stays archived because archived
projects are excluded from the model packet (so the model can't re-propose them). Revival is still
possible if real new mail matches the project (apply's reversible-closure path).

Dry by default — prints what WOULD change. Pass --apply to write it (backs up projects.json first).

    uv run python scripts/june_reset.py                 # dry: show the plan
    uv run python scripts/june_reset.py --apply         # write it (with backup)
"""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

from digest_core.state import load_projects, write_projects


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-dir", default="state")
    ap.add_argument("--since", default="2026-06-01")
    ap.add_argument(
        "--keep",
        default="",
        help="comma-separated project_ids to KEEP active despite no June activity (billing-based rescues)",
    )
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    pfile = Path(args.state_dir) / "projects.json"
    projects = load_projects(pfile)
    keep_ids = {s.strip() for s in args.keep.split(",") if s.strip()}

    def june_active(p) -> bool:
        return bool(p.last_activity_date) and p.last_activity_date >= args.since

    def survives(
        p,
    ) -> bool:  # kept active: June activity OR an explicit billing-based rescue
        return june_active(p) or p.project_id in keep_ids

    closed = [p for p in projects if p.status in ("done", "archived")]
    keep = [p for p in projects if p.status not in ("done", "archived") and survives(p)]
    archive = [
        p for p in projects if p.status not in ("done", "archived") and not survives(p)
    ]

    def todos(ps) -> int:
        return sum(len(p.open_todos) for p in ps)

    print(
        f"{len(projects)} projects: {len(closed)} already done/archived, "
        f"{len(keep)} kept ({todos(keep)} todos), {len(archive)} to archive ({todos(archive)} todos drop)\n"
    )
    print("── ARCHIVE (no activity since {}): ──".format(args.since))
    for p in sorted(archive, key=lambda p: p.last_activity_date or ""):
        print(
            f"  {p.last_activity_date or '  (none)  '}  {p.client_id} — {p.title!r}  [{len(p.open_todos)} todos]"
        )
    print("\n── KEEP active: ──")
    for p in sorted(keep, key=lambda p: p.last_activity_date or "", reverse=True):
        print(
            f"  {p.last_activity_date}  {p.client_id} — {p.title!r}  [{len(p.open_todos)} todos]"
        )

    if not args.apply:
        print("\n(dry run — nothing changed. Re-run with --apply to write.)")
        return

    backup = pfile.with_suffix(f".json.bak-{datetime.now():%Y%m%d-%H%M%S}")
    shutil.copy2(pfile, backup)
    for p in archive:
        p.status = "archived"
        p.status_agent = (
            "archived"  # keep the derived status stable on any future reprocessing
        )
        p.status_reason = f"June reset: no activity since {args.since}"
    write_projects(projects, pfile)
    print(f"\nApplied. Backed up to {backup.name}. Archived {len(archive)} projects.")


if __name__ == "__main__":
    main()
