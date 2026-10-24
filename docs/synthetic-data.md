# Synthetic data

`src/ucleany/synth` simulates Ucleany from launch (1 May 2026) to the extract date (23 October 2026). The same seed always produces the same data: the fingerprint of the result is recorded in `legacy/report_snapshots/manifest.json` and checked by the tests and by the Databricks landing job.

## The business

- **Rome only**, 16 service zones with their own demand and short-let weights (the historic centre has more short-let hosts, Prati and Parioli more households).
- **Customers:** households (78%), short-let hosts (14%), offices (8%). Households book one-off, monthly, every two weeks or weekly; hosts book turnovers that follow tourism seasonality; offices book weekly or twice a week.
- **Growth:** new customers follow an S-curve from launch, with August at about half the usual rate.
- **Seven services** from regular cleaning (€21.90/h) to post-renovation (€32.90/h) and flat-price short-let turnovers (€59). A new price list (+5%) starts on 1 September 2026.
- **Cleaners** are hired as booked hours grow, always with spare capacity, and about 3.5% leave each month after a two-month probation. They are promoted to senior after a 120-day review when well rated, which raises their pay rate: payouts depend on the level at the time of the job.
- **Lifecycle:** about 7% of bookings are cancelled by the customer (late cancellations pay a 50% fee), 2% by the cleaner (60% of those are reassigned), under 1% are no-shows. About 55% of completed jobs get a review.
- **Payments:** a charge after each completed job, failed attempts retried the next day, partial refunds after complaints, cancellation fees.
- **Marketing:** monthly spend by channel derived from acquisitions and channel CAC, plus a launch campaign.

## Defects the legacy database carries

| Defect | How it is planted | How the lakehouse handles it |
| --- | --- | --- |
| Duplicate accounts | 1.5% of people sign up again with a re-cased email | `silver.customer_identity` |
| Duplicate payment webhooks | 0.4% of succeeded charges inserted twice, same `provider_txn_id` | `fct_payments.is_duplicate` |
| Ratings of 0 and 6 | 1.2% of reviews before 15 July 2026 | `silver.reviews_quarantine` |
| Internal QA accounts | 12 `@ucleany.test` accounts with real bookings and payments | excluded from gold |
| Email casing and stray spaces | 14% of emails | `normalize_email` |
| Five phone formats | every customer and cleaner | `normalize_phone` (E.164) |
| City typed freely | "ROMA", "Rome", "Roma (RM)", ... | `normalize_city` |
| Local time in the source | `bookings.scheduled_start` stored in Rome time | `local_to_utc` |
| GDPR erasure | 3% of short-lived customers anonymised | `is_erased`, no PII |
| Moderated reviews | 1% deleted | AUTO CDC deletes |

`dataset.truth` lists every defective row, so the tests assert that each one is caught exactly, not approximately.

## Volume

| Table | Rows (current state) | Change rows extracted |
| --- | ---: | ---: |
| customers | 1,271 | 1,310 |
| cleaners | 121 | 141 |
| bookings | 7,438 | 14,109 |
| payments | 6,495 | 6,495 |
| reviews | 3,156 | 3,216 |

`--scale` multiplies acquisition volume for load and performance tests.
