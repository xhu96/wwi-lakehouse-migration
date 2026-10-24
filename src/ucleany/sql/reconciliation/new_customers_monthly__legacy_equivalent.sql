-- Legacy rule: every account counts, and the month is taken from the UTC timestamp.
SELECT
    trunc(to_date(c.signup_at), 'MM') AS month_start,
    z.city,
    c.acquisition_channel_id AS channel_id,
    COUNT(DISTINCT c.customer_id) AS new_customers
FROM {catalog}.silver.customers c
JOIN {catalog}.silver.zones z ON z.zone_id = c.zone_id
WHERE c.__END_AT IS NULL
  AND NOT c.is_test_account
  AND c.signup_at >= TIMESTAMP'{from_month} 00:00:00' AND c.signup_at < CAST(add_months(DATE'{to_month}', 1) AS TIMESTAMP)
GROUP BY 1, 2, 3
