# Contributing to AngelNet

Start with a reproducible issue, a small fixture and an expected outcome. Preserve the distinction between observed evidence and inferred maintenance status.

1. Run `npm ci --ignore-scripts --no-audit --no-fund`.
2. Run `npm test` and `npm run check:docs`.
3. Add tests for parser boundaries, limits or provenance when changing ingestion.
4. Keep generated indexes, archived page bodies, credentials and machine identifiers out of commits.
5. Document any change to schema, embedding identity, network destinations or default budgets.

Native RuVector tests must exercise the native backend. A missing native package is an environment failure, not a passing test. Changing the embedding model requires a new store and an explicit migration plan.

Tests should use local fixtures. External provider availability belongs in separately labeled execution evidence. Do not convert a timeout into an empty successful discovery result.

The project has not selected a distribution license yet. Dependency licenses remain with their respective authors.
