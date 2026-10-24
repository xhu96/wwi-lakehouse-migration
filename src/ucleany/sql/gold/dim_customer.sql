-- Customer dimension, SCD type 2. No direct identifiers (name, email, phone):
-- gold is readable by every analyst, personal data stays in silver.
-- The first version is valid from 1900-01-01 so facts never miss a match.
WITH versions AS (
    SELECT
        c.*,
        ROW_NUMBER() OVER (PARTITION BY c.customer_id ORDER BY c.__START_AT) AS version_no
    FROM {catalog}.silver.customers c
)
SELECT
    xxhash64(v.customer_id, v.__START_AT) AS customer_sk,
    v.customer_id,
    i.master_customer_id,
    i.is_duplicate_account,
    v.segment,
    v.zone_id,
    z.zone_name,
    z.city,
    v.acquisition_channel_id AS channel_id,
    ch.channel_name,
    to_date(from_utc_timestamp(v.signup_at, 'Europe/Rome')) AS signup_date,
    v.email_domain,
    v.marketing_opt_in,
    v.is_erased,
    CASE WHEN v.version_no = 1 THEN TIMESTAMP'1900-01-01 00:00:00' ELSE v.__START_AT END AS valid_from,
    v.__END_AT AS valid_to,
    v.__END_AT IS NULL AS is_current
FROM versions v
JOIN {catalog}.silver.customer_identity i ON i.customer_id = v.customer_id
LEFT JOIN {catalog}.silver.zones z ON z.zone_id = v.zone_id
LEFT JOIN {catalog}.silver.channels ch ON ch.channel_id = v.acquisition_channel_id
WHERE NOT i.is_test_account
