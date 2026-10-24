-- Calendar from the first booking year to the end of the following year.
-- Public holidays are the national ones plus 29 June (Santi Pietro e Paolo, Rome).
WITH bounds AS (
    SELECT
        trunc(min(service_date), 'YEAR') AS first_day,
        date_add(add_months(trunc(max(service_date), 'YEAR'), 24), -1) AS last_day
    FROM {catalog}.silver.bookings
),
days AS (
    SELECT explode(sequence(first_day, last_day, INTERVAL 1 DAY)) AS d FROM bounds
),
easter_monday AS (
    SELECT * FROM VALUES (DATE'2026-04-06'), (DATE'2027-03-29'), (DATE'2028-04-17') AS t(d)
),
enriched AS (
    SELECT
        days.d,
        (dayofweek(days.d) + 5) % 7 + 1 AS iso_dow,
        easter_monday.d IS NOT NULL AS is_easter_monday
    FROM days
    LEFT JOIN easter_monday ON easter_monday.d = days.d
)
SELECT
    CAST(date_format(d, 'yyyyMMdd') AS INT) AS date_key,
    d AS date,
    year(d) AS year,
    quarter(d) AS quarter,
    month(d) AS month,
    trunc(d, 'MM') AS month_start,
    date_format(d, 'yyyy-MM') AS year_month,
    element_at(array('Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno', 'Luglio', 'Agosto',
                     'Settembre', 'Ottobre', 'Novembre', 'Dicembre'), month(d)) AS month_name_it,
    weekofyear(d) AS iso_week,
    date_sub(d, iso_dow - 1) AS week_start,
    iso_dow AS day_of_week,
    element_at(array('Lunedi', 'Martedi', 'Mercoledi', 'Giovedi', 'Venerdi', 'Sabato', 'Domenica'), iso_dow) AS day_name_it,
    iso_dow >= 6 AS is_weekend,
    (date_format(d, 'MM-dd') IN ('01-01', '01-06', '04-25', '05-01', '06-02', '06-29', '08-15', '11-01', '12-08', '12-25', '12-26')
        OR is_easter_monday) AS is_public_holiday
FROM enriched
