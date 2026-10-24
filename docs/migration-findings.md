# Migration findings

The reconciliation compares every cell of the four legacy reports with the lakehouse. Three metrics differ. For each one, recomputing the lakehouse with the legacy rule reproduces the legacy number exactly, so the whole difference is explained by the rule change below. Figures cover May to October 2026 (extract of 23 October 2026).

## 1. Duplicate payment webhooks inflated cash collected

| | Legacy | Lakehouse | Difference |
| --- | ---: | ---: | ---: |
| Cash collected, May to Oct 2026 | €407,017.12 | €405,481.67 | −€1,535.45 (−0.38%) |

**Cause.** The payment provider retries a webhook when the first acknowledgement times out. Each delivery inserts a row in `ops.payments`, so one transaction can appear twice with the same `provider_txn_id`. `rpt.usp_MonthlyRevenueByZone` sums every succeeded row.

**Rule in the lakehouse.** A provider transaction counts once (`fct_payments.counts_as_cash`). Duplicates stay visible with `is_duplicate = true`, so finance can trace them.

**Affected:** 21 of 95 zone-month cells.

## 2. Duplicate accounts inflated new customers

| | Legacy | Lakehouse | Difference |
| --- | ---: | ---: | ---: |
| New customers, May to Oct 2026 | 1,259 | 1,251 | −8 (−0.6%) |

**Cause.** The app treats emails as case sensitive, so `giulia.rossi@gmail.com` and `Giulia.Rossi@Gmail.com` can open two accounts. `rpt.usp_NewCustomersMonthly` counts accounts, and it takes the month from the UTC timestamp, so a signup at 00:30 on the 1st in Rome lands in the previous month.

**Rule in the lakehouse.** A customer is a person: accounts with the same email at signup (trimmed, lower case) share a `master_customer_id`, and the earliest account is the master. Months follow Rome time. CAC is computed on people, so the legacy pack understated it slightly.

**Affected:** 10 of 36 month-channel cells.

## 3. Impossible ratings skewed cleaner averages

| | Legacy | Lakehouse |
| --- | ---: | ---: |
| Reviews counted | 3,130 | 3,124 |
| Ratings of 0 or 6 | 6 included | 6 quarantined |

**Cause.** Until the app release of 15 July 2026, the rating field had no server-side validation and `ops.reviews.rating` has no CHECK constraint. `rpt.usp_CleanerMonthly` averages every stored rating, and that average feeds the cleaner bonus calculation.

**Rule in the lakehouse.** Ratings outside 1 to 5 go to `silver.reviews_quarantine` and are excluded from gold. A pipeline expectation (`rating_in_range`) counts new ones, so a regression in the app shows up the same day.

**Affected:** 6 cleaner-months, on both review count and average.

## What matched exactly

Completed bookings, billed hours, booking value and cleaner payouts by zone and month, bookings by status, and cleaner bookings, hours and payouts by month: 1,475 cells, all equal to the cent.

## Also cleaned on the way

These did not change any legacy report, but they would have broken the new model:

- 12 internal QA accounts (`@ucleany.test`) excluded from gold. The legacy reports filtered them with a `LIKE` in every procedure; the lakehouse flags them once in silver.
- Phone numbers in five formats normalised to E.164.
- City typed by customers ("ROMA", "Rome", "Roma (RM)") normalised.
- Booking times stored in Rome local time converted to UTC once, in silver, with daylight saving handled.
- GDPR erasures (anonymised accounts) kept as accounts but with no personal data.
- Reviews removed by moderation applied as deletes by AUTO CDC.
