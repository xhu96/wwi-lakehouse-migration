# ADR 0001: Lakeflow declarative pipelines with AUTO CDC

**Status:** accepted · **Date:** 2026-10

## Context

The source is a change feed from SQL Server: inserts, updates and deletes, delivered as parquet files. Rows can arrive late or out of order across files, and some tables need history. The team is small, so whatever we build has to be operable by one person.

## Options

1. Notebooks with hand-written `MERGE INTO`, scheduled by a job.
2. Lakeflow declarative pipelines: Auto Loader for ingestion, AUTO CDC for applying changes, materialized views for gold.
3. dbt on a SQL warehouse, with ingestion done separately.

## Decision

Option 2. AUTO CDC handles ordering by `_commit_ts`, deletes and SCD type 2 out of the box, which is exactly the logic that tends to be wrong in hand-written MERGEs. Expectations give data quality metrics per table without extra tooling, and the pipeline graph shows lineage from file to KPI. Serverless removes cluster management.

## Consequences

- Pipeline code uses the `dlt` module, which is not available outside Databricks. Transformations are therefore kept in plain PySpark functions and SQL files (ADR 0003) so they can be tested locally.
- Gold tables are materialized views: refreshes are incremental where the engine can manage it, full otherwise. At current volume (thousands of rows per table) a full refresh is cheap.
- `create_auto_cdc_flow` replaced `apply_changes`; the pipeline uses whichever the runtime provides.
