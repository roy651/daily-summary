"""digest_core — daily-summary's domain package.

Reads conditioned correspondence (via the shared, portable `mail_evidence` engine) and reasons
out a read-only morning digest: project status, last-24h updates, and a prioritized TODO list.

The package is intentionally split into a deterministic layer (state, packet, apply, todos,
render, delivery) and a single swappable MODEL PASS (`reasoner`). See `docs/` for the contracts.
"""

__version__ = "0.1.0"
