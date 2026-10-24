# Data model and metric definitions

## Layers

| Schema | Content | Who reads it |
| --- | --- | --- |
| `landing` | Volume `cdc`: parquet change files from the SQL Server extract | pipeline only |
| `bronze` | Change rows as extracted, append only, with source file and ingestion time | data engineers |
| `silver` | Typed, cleaned, changes applied (SCD1, SCD2 for customers and cleaners). Contains personal data | data engineers, restricted |
| `gold` | Star schema and KPI tables. No direct identifiers | analysts, Power BI |

## Metrics

| Metric | Definition | Where |
| --- | --- | --- |
| Completed booking | Booking with status `completed` | `fct_bookings.is_completed` |
| GMV | Net amount of completed bookings plus cancellation fees, after discounts, VAT included | `fct_bookings.gmv_eur` |
| Platform revenue | GMV minus cleaner payouts | `fct_bookings.platform_revenue_eur` |
| Take rate | Platform revenue / GMV | `agg_kpi_monthly.take_rate` |
| Cash collected | Succeeded payments, each provider transaction once, refunds negative | `fct_payments.cash_eur` |
| Active customer | Person (master customer) with at least one completed booking in the month | `agg_kpi_monthly.active_customers` |
| New customer (activation) | Person whose first completed booking falls in the month | `fct_bookings.is_first_completed_booking` |
| New customer (signup) | Person whose first account was created in the month, Rome time | reconciliation, `dim_customer.signup_date` |
| Blended CAC | Marketing spend / new customers (activation) | `agg_kpi_monthly.blended_cac_eur` |
| Cancellation rate | Bookings cancelled by customer or cleaner / all bookings in the month | `agg_kpi_monthly.cancellation_rate` |
| Utilisation | Billed hours / hours offered (weekly capacity × active days / 7) | `agg_cleaner_monthly.utilisation` |
| Average rating | Mean of valid ratings (1 to 5) | `fct_reviews`, `agg_*` |
| Retention | Share of a cohort with a completed booking N months after the first | `agg_customer_cohorts.retention_rate` |

## Conventions

- Service dates and months follow Europe/Rome time. Stored timestamps are UTC.
- Money is `DECIMAL(12,2)` in euro.
- Surrogate keys of SCD2 dimensions are `xxhash64(natural key, version start)`. The first version is valid from 1900-01-01 so a fact can never miss its dimension row.
- Test accounts never reach gold.
