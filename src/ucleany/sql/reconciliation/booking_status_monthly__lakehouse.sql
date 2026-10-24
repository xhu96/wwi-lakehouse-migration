SELECT
    trunc(f.service_date, 'MM') AS month_start,
    z.city,
    f.status,
    COUNT(*) AS bookings
FROM {catalog}.gold.fct_bookings f
JOIN {catalog}.gold.dim_zone z ON z.zone_id = f.zone_id
WHERE f.service_date >= DATE'{from_month}' AND f.service_date < add_months(DATE'{to_month}', 1)
GROUP BY 1, 2, 3
