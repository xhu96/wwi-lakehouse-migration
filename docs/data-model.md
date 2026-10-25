# Data model and metric definitions

## Layers

| Schema | Content | Who reads it |
| --- | --- | --- |
| `landing` | Volume `cdc`: parquet change files from the SQL Server extract | data engineers |
| `bronze` | Change rows as extracted, append only, with source file and ingestion time | data engineers |
| `silver` | Typed, cleaned, changes applied (SCD1, SCD2 for customers and cleaners). Contains personal data, masked for most readers | engineers; analysts and customer care through column masks |
| `gold` | Star schema and KPI tables. No direct identifiers | analysts, leadership, Power BI; zone managers through a row filter |
| `governance` | Zone entitlements, mask and row filter functions | engineers, Power BI (entitlements only) |

Access is defined in [governance/policy.yml](../governance/policy.yml); see [governance.md](governance.md).

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
| Cancellation rate | Bookings cancelled by customer or cleaner / closed bookings (all but `confirmed`) in the month | `agg_kpi_monthly.cancellation_rate` |
| Utilisation | Billed hours / hours offered (weekly capacity × active days / 7) | `agg_cleaner_monthly.utilisation` |
| Average rating | Mean of valid ratings (1 to 5) | `fct_reviews`, `agg_*` |
| Retention | Share of a cohort with a completed booking N months after the first | `agg_customer_cohorts.retention_rate` |

## Conventions

- Service dates and months follow Europe/Rome time. Stored timestamps are UTC.
- Money is `DECIMAL(12,2)` in euro.
- Surrogate keys of SCD2 dimensions are `xxhash64(natural key, version start)`. The first version is valid from 1900-01-01 so a fact can never miss its dimension row.
- Test accounts never reach gold.

## Power BI semantic model

The model in [powerbi/](../powerbi/README.md) imports the gold tables and implements the same definitions as DAX measures, so a number in a report and the same number in `agg_kpi_monthly` agree.

| Gold column | Measure |
| --- | --- |
| `agg_kpi_monthly.bookings` | `[Closed Bookings]` |
| `agg_kpi_monthly.gmv_eur` | `[GMV]` |
| `agg_kpi_monthly.take_rate` | `[Take Rate]` |
| `agg_kpi_monthly.active_customers` | `[Active Customers]` |
| `agg_kpi_monthly.new_customers` | `[New Customers]` |
| `agg_kpi_monthly.blended_cac_eur` | `[CAC]` |
| `agg_kpi_monthly.refunds_eur` | `[Refunds]` |
| `agg_cleaner_monthly.utilisation` | `[Cleaner Utilisation]` |
| `agg_customer_cohorts.retention_rate` | `[Retention Rate]` |
