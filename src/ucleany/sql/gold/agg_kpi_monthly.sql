-- Monthly business KPIs: the numbers the founders' board pack is built on.
WITH bookings AS (
    SELECT
        trunc(f.service_date, 'MM') AS month_start,
        COUNT(*) AS bookings,
        SUM(CASE WHEN f.is_completed THEN 1 ELSE 0 END) AS completed_bookings,
        SUM(CASE WHEN f.is_cancelled THEN 1 ELSE 0 END) AS cancelled_bookings,
        SUM(f.billed_hours) AS billed_hours,
        SUM(f.gmv_eur) AS gmv_eur,
        SUM(f.platform_revenue_eur) AS platform_revenue_eur,
        SUM(f.cleaner_payout) AS cleaner_payout_eur,
        SUM(f.discount_amount) FILTER (WHERE f.is_completed) AS discounts_eur,
        COUNT(DISTINCT CASE WHEN f.is_completed THEN f.master_customer_id END) AS active_customers,
        COUNT(DISTINCT CASE WHEN f.is_completed THEN f.cleaner_id END) AS active_cleaners,
        SUM(CASE WHEN f.is_first_completed_booking THEN 1 ELSE 0 END) AS new_customers
    FROM {catalog}.gold.fct_bookings f
    WHERE f.status <> 'confirmed'
    GROUP BY trunc(f.service_date, 'MM')
),
refunds AS (
    SELECT trunc(service_date, 'MM') AS month_start, -SUM(cash_eur) AS refunds_eur
    FROM {catalog}.gold.fct_payments
    WHERE payment_type = 'refund' AND counts_as_cash
    GROUP BY trunc(service_date, 'MM')
),
ratings AS (
    SELECT trunc(service_date, 'MM') AS month_start, AVG(rating) AS avg_rating, COUNT(*) AS reviews
    FROM {catalog}.gold.fct_reviews
    GROUP BY trunc(service_date, 'MM')
),
spend AS (
    SELECT month_start, SUM(spend_eur) AS marketing_spend_eur
    FROM {catalog}.gold.fct_marketing_spend
    GROUP BY month_start
)
SELECT
    b.month_start,
    b.bookings,
    b.completed_bookings,
    b.cancelled_bookings,
    ROUND(b.cancelled_bookings / b.bookings, 4) AS cancellation_rate,
    b.billed_hours,
    b.gmv_eur,
    b.platform_revenue_eur,
    ROUND(b.platform_revenue_eur / NULLIF(b.gmv_eur, 0), 4) AS take_rate,
    b.cleaner_payout_eur,
    b.discounts_eur,
    COALESCE(r.refunds_eur, 0) AS refunds_eur,
    b.active_customers,
    b.new_customers,
    b.active_cleaners,
    ROUND(b.gmv_eur / NULLIF(b.completed_bookings, 0), 2) AS avg_order_value_eur,
    rt.avg_rating,
    rt.reviews,
    s.marketing_spend_eur,
    ROUND(s.marketing_spend_eur / NULLIF(b.new_customers, 0), 2) AS blended_cac_eur
FROM bookings b
LEFT JOIN refunds r ON r.month_start = b.month_start
LEFT JOIN ratings rt ON rt.month_start = b.month_start
LEFT JOIN spend s ON s.month_start = b.month_start
