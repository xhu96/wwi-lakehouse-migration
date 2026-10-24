-- Retention by cohort: customers grouped by the month of their first completed job.
WITH firsts AS (
    SELECT master_customer_id, trunc(service_date, 'MM') AS cohort_month
    FROM {catalog}.gold.fct_bookings
    WHERE is_first_completed_booking
),
activity AS (
    SELECT master_customer_id, trunc(service_date, 'MM') AS activity_month, SUM(gmv_eur) AS gmv_eur
    FROM {catalog}.gold.fct_bookings
    WHERE is_completed
    GROUP BY 1, 2
),
sizes AS (
    SELECT cohort_month, COUNT(*) AS cohort_size FROM firsts GROUP BY cohort_month
)
SELECT
    f.cohort_month,
    CAST(months_between(a.activity_month, f.cohort_month) AS INT) AS months_since_first,
    s.cohort_size,
    COUNT(DISTINCT a.master_customer_id) AS active_customers,
    ROUND(COUNT(DISTINCT a.master_customer_id) / s.cohort_size, 4) AS retention_rate,
    SUM(a.gmv_eur) AS gmv_eur
FROM firsts f
JOIN activity a ON a.master_customer_id = f.master_customer_id
JOIN sizes s ON s.cohort_month = f.cohort_month
GROUP BY f.cohort_month, CAST(months_between(a.activity_month, f.cohort_month) AS INT), s.cohort_size
