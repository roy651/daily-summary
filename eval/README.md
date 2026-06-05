# eval/ (git-ignored)

The manufactured ground-truth evaluation set (daily-summary has no invoice-style oracle). Real
correspondence is embedded in the digests here, so everything except this README is git-ignored.

Layout:
- `gt/<date>.md`, `gt/<date>.json` — Avigail's ground-truth digest/todos for a replayed day.
- (scorer output may also land here.)

See `docs/07-acceptance.md` for the backtest + scoring loop.
