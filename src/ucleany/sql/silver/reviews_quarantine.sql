-- Reviews that fail validation. Kept for the product team, excluded from gold metrics.
SELECT
    review_id,
    booking_id,
    cleaner_id,
    rating,
    created_at,
    'rating_out_of_range' AS reason
FROM {catalog}.silver.reviews
WHERE NOT is_valid_rating
