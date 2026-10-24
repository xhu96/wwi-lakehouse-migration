SELECT
    month_start,
    CAST(date_format(month_start, 'yyyyMMdd') AS INT) AS date_key,
    city,
    channel_id,
    spend_eur
FROM {catalog}.silver.marketing_spend
