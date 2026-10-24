-- Cleaner dimension, SCD type 2 (level, home zone, offboarding).
WITH versions AS (
    SELECT
        c.*,
        ROW_NUMBER() OVER (PARTITION BY c.cleaner_id ORDER BY c.__START_AT) AS version_no
    FROM {catalog}.silver.cleaners c
)
SELECT
    xxhash64(v.cleaner_id, v.__START_AT) AS cleaner_sk,
    v.cleaner_id,
    concat(v.first_name, ' ', left(v.last_name, 1), '.') AS cleaner_display_name,
    v.home_zone_id AS zone_id,
    z.zone_name,
    v.contract_type,
    v.level,
    v.weekly_capacity_hours,
    to_date(from_utc_timestamp(v.onboarded_at, 'Europe/Rome')) AS onboarded_date,
    to_date(from_utc_timestamp(v.offboarded_at, 'Europe/Rome')) AS offboarded_date,
    CASE WHEN v.version_no = 1 THEN TIMESTAMP'1900-01-01 00:00:00' ELSE v.__START_AT END AS valid_from,
    v.__END_AT AS valid_to,
    v.__END_AT IS NULL AS is_current
FROM versions v
LEFT JOIN {catalog}.silver.zones z ON z.zone_id = v.home_zone_id
