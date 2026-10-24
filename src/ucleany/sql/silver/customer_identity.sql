-- One row per customer account, mapped to the person behind it.
-- Accounts that signed up with the same email (ignoring case and spaces) are the
-- same person: the earliest account is the master. The email at signup is used,
-- so a later GDPR erasure does not split an identity.
WITH first_version AS (
    SELECT
        customer_id,
        email,
        signup_at,
        is_test_account,
        ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY __START_AT) AS version_no
    FROM {catalog}.silver.customers
),
accounts AS (
    SELECT * FROM first_version WHERE version_no = 1
)
SELECT
    customer_id,
    FIRST_VALUE(customer_id) OVER (PARTITION BY email ORDER BY signup_at, customer_id) AS master_customer_id,
    customer_id <> FIRST_VALUE(customer_id) OVER (PARTITION BY email ORDER BY signup_at, customer_id) AS is_duplicate_account,
    is_test_account
FROM accounts
