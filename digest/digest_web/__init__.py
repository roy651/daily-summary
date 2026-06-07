"""digest_web — Avigail's local dashboard (docs/08-dashboard.md).

FastAPI + Jinja2 + HTMX. Reads the merged state `digest_core` produces and lets Avigail interact
(close/edit/add todos, change status, add/dismiss notes, revive). Her actions are written as
tombstones in the single shared state model (never a sidecar). This package imports `digest_core`;
it is never imported into it.
"""
