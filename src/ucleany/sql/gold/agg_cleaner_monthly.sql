-- Cleaner productivity by month: hours worked against the capacity they offered.
WITH months AS (
    SELECT DISTINCT month_start, last_day(month_start) AS month_end
    FROM {catalog}.gold.dim_date
    WHERE date BETWEEN (SELECT min(service_date) FROM {catalog}.gold.fct_bookings)
                   AND (SELECT max(service_date) FROM {catalog}.gold.fct_bookings WHERE is_completed)
),
as_of AS (
    SELECT max(service_date) AS as_of_date FROM {catalog}.gold.fct_bookings WHERE is_completed
),
cleaners AS (
    SELECT cleaner_id, cleaner_display_name, zone_name, level, weekly_capacity_hours, onboarded_date, offboarded_date
    FROM {catalog}.gold.dim_cleaner
    WHERE is_current
),
active AS (
    SELECT
        m.month_start,
        c.*,
        datediff(
            least(m.month_end, coalesce(date_sub(c.offboarded_date, 1), m.month_end), a.as_of_date),
            greatest(m.month_start, c.onboarded_date)
        ) + 1 AS active_days
    FROM months m
    CROSS JOIN as_of a
    JOIN cleaners c
      ON c.onboarded_date <= m.month_end
     AND (c.offboarded_date IS NULL OR c.offboarded_date > m.month_start)
),
work AS (
    SELECT trunc(service_date, 'MM') AS month_start, cleaner_id,
           COUNT(*) AS completed_bookings, SUM(billed_hours) AS billed_hours, SUM(cleaner_payout) AS cleaner_payout_eur
    FROM {catalog}.gold.fct_bookings
    WHERE is_completed
    GROUP BY 1, 2
),
quality AS (
    SELECT trunc(service_date, 'MM') AS month_start, cleaner_id, COUNT(*) AS reviews, AVG(rating) AS avg_rating
    FROM {catalog}.gold.fct_reviews
    GROUP BY 1, 2
)
SELECT
    a.month_start,
    a.cleaner_id,
    a.cleaner_display_name,
    a.zone_name,
    a.level,
    a.active_days,
    ROUND(a.weekly_capacity_hours * a.active_days / 7.0, 1) AS capacity_hours,
    COALESCE(w.completed_bookings, 0) AS completed_bookings,
    COALESCE(w.billed_hours, 0) AS billed_hours,
    COALESCE(w.cleaner_payout_eur, 0) AS cleaner_payout_eur,
    ROUND(COALESCE(w.billed_hours, 0) / NULLIF(a.weekly_capacity_hours * a.active_days / 7.0, 0), 3) AS utilisation,
    COALESCE(q.reviews, 0) AS reviews,
    q.avg_rating
FROM active a
LEFT JOIN work w ON w.month_start = a.month_start AND w.cleaner_id = a.cleaner_id
LEFT JOIN quality q ON q.month_start = a.month_start AND q.cleaner_id = a.cleaner_id
WHERE a.active_days > 0
