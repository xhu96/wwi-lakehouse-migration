# ADR 0007: Power BI semantic model as code (PBIP and TMDL)

**Status:** accepted · **Date:** 2026-10

## Context

The legacy Excel pack recomputed every metric in each workbook, and two workbooks rarely agreed. Moving to Power BI only helps if the metric definitions live in one governed model that every report reuses, and if a change to that model can be reviewed like code.

## Decision

- One shared semantic model, saved as a Power BI Project (PBIP) with the model in TMDL, so every table, measure and role is a readable text file in git.
- Import mode over the gold schema of the Databricks SQL warehouse. Volumes are small (thousands of rows a month), so import gives the fastest reports and the cheapest warehouse; DirectQuery can be revisited at 10x volume.
- All business logic in explicit measures with descriptions, format strings and display folders; implicit measures are disabled. Definitions mirror the gold KPI tables ([data-model.md](../data-model.md)).
- Time intelligence as one calculation group instead of a copy of each measure per period.
- Payments join the calendar on service date (matching the legacy report) with an inactive relationship on payment date for cash-flow views.
- Dynamic RLS from `governance.zone_access`, the table behind the Unity Catalog row filter ([ADR 0006](0006-governance-as-code.md)), with a filter expression instead of a bidirectional relationship.
- CI loads the model with the Analysis Services object model (TOM) and enforces the team's rules: descriptions, format strings, DIVIDE instead of `/`, hidden keys, fixed decimal for money, no bidirectional filters, a marked date table, and every column, measure and table referenced in DAX or in a report visual must exist.

## Consequences

- A broken reference fails the pull request instead of a report in production.
- The model cannot be refreshed in CI (that needs the Analysis Services engine and a warehouse), so numeric checks stay in the lakehouse reconciliation; the model check is structural.
- Report authors build thin reports on the shared model and cannot redefine metrics.
