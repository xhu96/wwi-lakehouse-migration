# ADR 0003: One set of SQL models for Databricks and for CI

**Status:** accepted · **Date:** 2026-10

## Context

A pipeline that only runs in a workspace is tested late and expensively. We want every pull request to build the whole lakehouse and reconcile it with the legacy reports, in a few minutes, without workspace credentials.

## Decision

- Silver cleansing rules are PySpark functions in `ucleany.transforms`, and a single registry (`CDC_TABLES`) declares keys, SCD type and data quality rules for each table.
- Silver models, gold models and reconciliation queries are SQL files in `ucleany/sql`, referencing tables as `{catalog}.<schema>.<table>`.
- On Databricks the pipeline renders them with the Unity Catalog catalog. In CI the local runner renders them with `spark_catalog` and emulates AUTO CDC with window functions (`apply_scd1`, `apply_scd2`), which have their own unit tests.

## Consequences

- The SQL is Spark SQL that runs on both open source Spark and Databricks; Databricks-only syntax is avoided in models.
- Readers find the business logic in plain SQL, which is what analysts review.
- The CDC emulation is only as good as its tests. It covers ordering, deletes and version boundaries; it does not try to reproduce late-arriving data handling across batches.
