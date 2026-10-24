# ADR 0002: SCD type 2 for customers and cleaners, type 1 elsewhere

**Status:** accepted · **Date:** 2026-10

## Context

Cleaner pay depends on their level (standard, senior, top), and levels change after reviews. Customers move between zones. Reports must show what was true when a job happened, not what is true today. Bookings, payments and reviews only need their latest state.

## Decision

- `silver.customers` and `silver.cleaners` keep every version (AUTO CDC `stored_as_scd_type=2`).
- All other silver tables keep the current state (type 1).
- Gold dimensions get a surrogate key per version, `xxhash64(natural key, version start)`. Facts join the version valid at the job's start time in UTC.
- The first version of each dimension row is valid from 1900-01-01, so a booking scheduled minutes before an onboarding timestamp still finds its cleaner.

## Consequences

- Payout by level can be explained to the cent from gold alone.
- Power BI relationships use the surrogate keys; "current" attributes come from `is_current`.
- Type 1 tables lose intermediate states (for example a booking's original cleaner). The change rows remain in bronze if a question ever needs them.
