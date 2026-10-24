# ADR 0004: Reconciliation with the legacy reports is a gate

**Status:** accepted · **Date:** 2026-10

## Context

People trust the Excel pack because they have used it for months. A new platform that shows different numbers without an explanation will not be adopted, even when it is right.

## Decision

- The output of each legacy stored procedure is exported from SQL Server and committed (`legacy/report_snapshots`). CI rebuilds the legacy database in a SQL Server container and fails if the export changes.
- Each report is recomputed from gold with the agreed business rules, and again with the legacy rules ("legacy equivalent").
- A cell is `MATCH` if legacy equals lakehouse, `EXPLAINED` if legacy equals the legacy equivalent and the metric has a documented rule change, and `BREAK` otherwise.
- Any break fails CI and the production job. Results are published to `gold.reconciliation_results` and `gold.reconciliation_summary`.

## Consequences

- Every accepted difference has a written reason, reviewed like code (`docs/migration-findings.md`).
- Changing a business rule requires updating the explanation and the legacy-equivalent query in the same pull request.
- When the legacy reports are switched off, the gate can be kept as a regression test against the frozen baseline.
