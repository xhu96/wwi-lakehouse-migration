-- Valid reviews only; out-of-range ratings are in silver.reviews_quarantine.
SELECT
    r.review_id,
    r.booking_id,
    CAST(date_format(to_date(from_utc_timestamp(r.created_at, 'Europe/Rome')), 'yyyyMMdd') AS INT) AS date_key,
    f.service_date,
    f.cleaner_id,
    f.cleaner_sk,
    f.master_customer_id,
    f.zone_id,
    f.service_id,
    r.rating,
    r.rating <= 2 AS is_detractor,
    r.comment IS NOT NULL AS has_comment,
    r.created_at
FROM {catalog}.silver.reviews r
JOIN {catalog}.gold.fct_bookings f ON f.booking_id = r.booking_id
WHERE r.is_valid_rating
