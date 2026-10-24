-- Legacy rule: every stored rating counts, including the out-of-range ones.
WITH jobs AS (
    SELECT trunc(service_date, 'MM') AS month_start, cleaner_id, booking_id, billed_hours, cleaner_payout
    FROM {catalog}.gold.fct_bookings
    WHERE is_completed
      AND service_date >= DATE'{from_month}' AND service_date < add_months(DATE'{to_month}', 1)
)
SELECT
    j.month_start,
    j.cleaner_id,
    COUNT(*) AS completed_bookings,
    SUM(j.billed_hours) AS billed_hours,
    SUM(j.cleaner_payout) AS cleaner_payout_eur,
    COUNT(r.review_id) AS reviews,
    ROUND(AVG(r.rating), 3) AS avg_rating
FROM jobs j
LEFT JOIN {catalog}.silver.reviews r ON r.booking_id = j.booking_id
GROUP BY j.month_start, j.cleaner_id
