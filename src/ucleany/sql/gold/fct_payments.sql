-- One row per payment record. The provider retries webhooks, so the same
-- transaction can appear more than once: only the first row counts as cash.
WITH p AS (
    SELECT
        p.*,
        ROW_NUMBER() OVER (PARTITION BY p.provider_txn_id ORDER BY p.created_at, p.payment_id) AS txn_row
    FROM {catalog}.silver.payments p
)
SELECT
    p.payment_id,
    p.booking_id,
    CAST(date_format(to_date(from_utc_timestamp(p.created_at, 'Europe/Rome')), 'yyyyMMdd') AS INT) AS date_key,
    p.created_at,
    p.payment_type,
    p.amount,
    p.status,
    p.provider_txn_id,
    p.txn_row > 1 AS is_duplicate,
    p.status = 'succeeded' AND p.txn_row = 1 AS counts_as_cash,
    CAST(CASE WHEN p.status = 'succeeded' AND p.txn_row = 1 THEN p.amount ELSE 0 END AS DECIMAL(12,2)) AS cash_eur,
    f.service_date,
    f.zone_id,
    f.cleaner_id,
    f.master_customer_id
FROM p
JOIN {catalog}.gold.fct_bookings f ON f.booking_id = p.booking_id
