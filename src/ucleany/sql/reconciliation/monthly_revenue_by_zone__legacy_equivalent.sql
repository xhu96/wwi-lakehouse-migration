-- Same report, recomputed from the lakehouse with the legacy rule for cash:
-- every succeeded payment row, duplicates included.
WITH b AS (
    SELECT trunc(service_date, 'MM') AS month_start, zone_id, booking_id, is_completed, billed_hours, net_amount, cleaner_payout
    FROM {catalog}.gold.fct_bookings
    WHERE service_date >= DATE'{from_month}' AND service_date < add_months(DATE'{to_month}', 1)
),
pay AS (
    SELECT booking_id, SUM(amount) AS paid
    FROM {catalog}.silver.payments
    WHERE status = 'succeeded'
    GROUP BY booking_id
)
SELECT
    b.month_start,
    b.zone_id,
    SUM(CASE WHEN b.is_completed THEN 1 ELSE 0 END) AS completed_bookings,
    SUM(b.billed_hours) AS billed_hours,
    SUM(CASE WHEN b.is_completed THEN b.net_amount ELSE 0 END) AS booking_value_eur,
    SUM(CASE WHEN b.is_completed THEN b.cleaner_payout ELSE 0 END) AS cleaner_payout_eur,
    COALESCE(SUM(pay.paid), 0) AS cash_collected_eur
FROM b
LEFT JOIN pay ON pay.booking_id = b.booking_id
GROUP BY b.month_start, b.zone_id
