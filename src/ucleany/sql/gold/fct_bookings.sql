-- One row per booking. Grain: booking_id. Test accounts are excluded.
-- Dimension keys point to the customer and cleaner versions valid when the job started.
WITH b AS (
    SELECT
        b.*,
        i.master_customer_id
    FROM {catalog}.silver.bookings b
    JOIN {catalog}.silver.customer_identity i ON i.customer_id = b.customer_id
    WHERE NOT i.is_test_account
),
first_completed AS (
    SELECT booking_id
    FROM (
        SELECT booking_id, ROW_NUMBER() OVER (PARTITION BY master_customer_id ORDER BY scheduled_start_utc, booking_id) AS n
        FROM b
        WHERE status = 'completed'
    )
    WHERE n = 1
)
SELECT
    b.booking_id,
    CAST(date_format(b.service_date, 'yyyyMMdd') AS INT) AS date_key,
    b.service_date,
    b.scheduled_start_local,
    b.scheduled_start_utc,
    dc.customer_sk,
    b.customer_id,
    b.master_customer_id,
    dcl.cleaner_sk,
    b.cleaner_id,
    b.service_id,
    b.zone_id,
    dc.channel_id,
    b.status,
    b.status = 'completed' AS is_completed,
    b.status IN ('cancelled_by_customer', 'cancelled_by_cleaner') AS is_cancelled,
    b.cancellation_fee > 0 AS is_charged_cancellation,
    fc.booking_id IS NOT NULL AS is_first_completed_booking,
    b.recurrence,
    b.promo_code,
    b.planned_hours,
    CASE WHEN b.status = 'completed' THEN b.billed_hours ELSE 0 END AS billed_hours,
    b.unit_price,
    b.gross_amount,
    b.discount_amount,
    b.net_amount,
    b.cancellation_fee,
    b.cleaner_payout,
    CAST(CASE WHEN b.status = 'completed' THEN b.net_amount ELSE 0 END + b.cancellation_fee AS DECIMAL(12,2)) AS gmv_eur,
    CAST(CASE WHEN b.status = 'completed' THEN b.net_amount - b.cleaner_payout ELSE 0 END + b.cancellation_fee AS DECIMAL(12,2)) AS platform_revenue_eur,
    ROUND((unix_timestamp(b.scheduled_start_utc) - unix_timestamp(b.created_at)) / 3600.0, 1) AS lead_time_hours,
    b.created_at,
    b.cancelled_at,
    b.completed_at
FROM b
LEFT JOIN first_completed fc ON fc.booking_id = b.booking_id
LEFT JOIN {catalog}.gold.dim_customer dc
    ON dc.customer_id = b.customer_id
   AND b.scheduled_start_utc >= dc.valid_from
   AND (dc.valid_to IS NULL OR b.scheduled_start_utc < dc.valid_to)
LEFT JOIN {catalog}.gold.dim_cleaner dcl
    ON dcl.cleaner_id = b.cleaner_id
   AND b.scheduled_start_utc >= dcl.valid_from
   AND (dcl.valid_to IS NULL OR b.scheduled_start_utc < dcl.valid_to)
