# ADR 0006: Governance as code, from one policy file

**Status:** accepted · **Date:** 2026-10

## Context

Access rules for the lakehouse were starting to live in three places: grants clicked in Catalog Explorer, an RLS role typed into Power BI Desktop, and a spreadsheet saying which zone manager covers which part of Rome. They drift apart, nobody can review a change, and an auditor asking "who can read customer emails?" gets a different answer from each.

## Decision

- [governance/policy.yml](../../governance/policy.yml) is the only definition of access: groups, catalog and schema grants, personal data classification, column masks, the zone row filter and the zone assignments.
- `src/ucleany/governance.py` turns it into SQL. Planning is a pure function, so tests check the policy without a workspace: raw layers closed to all but engineers, every name, email, phone and comment in silver masked, every classified column still existing after a rename, no personal column in any gold table.
- The `apply_governance` task runs after every pipeline update, so a new table is governed before anyone reads it. It also revokes direct grants to policy groups that the policy does not contain: a grant clicked in Catalog Explorer lasts until the next run.
- Zone managers are filtered by a Unity Catalog row filter on the gold facts that reads `governance.zone_access`. The Power BI model imports the same table for its dynamic RLS, so SQL users and report users see the same rows.
- Identity matching in silver runs on a SHA-256 hash of the normalised email, and gold reads the cleaner display name prepared in silver. No model downstream reads a masked column, so masks never change pipeline results.

## Consequences

- An access change is a pull request with a reviewer and a test run, and git history is the audit trail.
- Grants to groups that do not exist yet are skipped with a warning in dev and fail the job in prod (`governance_strict`).
- Row filters are applied only when the identity running the job is in an all-zones group; otherwise the filter would hide rows from the pipeline's own aggregates. In prod the job runs as a service principal in `ucleany-data-engineers`.
- Power BI RLS matches on the user principal name and Unity Catalog on the Databricks user name, so both must be the same corporate email.
