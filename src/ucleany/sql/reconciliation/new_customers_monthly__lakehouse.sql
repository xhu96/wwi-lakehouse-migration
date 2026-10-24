-- People, not accounts: duplicate sign-ups are folded into their master customer.
-- Month of signup in Rome time.
SELECT
    trunc(signup_date, 'MM') AS month_start,
    city,
    channel_id,
    COUNT(DISTINCT master_customer_id) AS new_customers
FROM {catalog}.gold.dim_customer
WHERE is_current
  AND NOT is_duplicate_account
  AND signup_date >= DATE'{from_month}' AND signup_date < add_months(DATE'{to_month}', 1)
GROUP BY 1, 2, 3
