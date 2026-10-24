-- Legacy reporting procedures.
-- These fed the monthly Excel pack and the SSRS reports before the migration.
-- They are kept as they were written, including the logic the migration had to
-- question (see docs/migration-findings.md).

USE ucleany_ops;
GO

/* Monthly revenue by service zone.
   Used by: finance monthly pack, "Ricavi per zona" tab. */
CREATE OR ALTER PROCEDURE rpt.usp_MonthlyRevenueByZone
    @FromMonth DATE,
    @ToMonth   DATE
AS
BEGIN
    SET NOCOUNT ON;

    ;WITH b AS (
        SELECT
            DATEFROMPARTS(YEAR(bk.scheduled_start), MONTH(bk.scheduled_start), 1) AS month_start,
            bk.zone_id,
            bk.booking_id,
            bk.status,
            bk.billed_hours,
            bk.net_amount,
            bk.cleaner_payout
        FROM ops.bookings bk
        JOIN ops.customers c ON c.customer_id = bk.customer_id
        WHERE c.email NOT LIKE '%@ucleany.test%'
          AND bk.scheduled_start >= @FromMonth
          AND bk.scheduled_start <  DATEADD(MONTH, 1, @ToMonth)
    ),
    pay AS (
        -- Every succeeded payment row for the booking: charges, fees and refunds.
        SELECT p.booking_id, SUM(p.amount) AS paid
        FROM ops.payments p
        WHERE p.status = 'succeeded'
        GROUP BY p.booking_id
    )
    SELECT
        b.month_start,
        b.zone_id,
        SUM(CASE WHEN b.status = 'completed' THEN 1 ELSE 0 END)                AS completed_bookings,
        SUM(CASE WHEN b.status = 'completed' THEN b.billed_hours ELSE 0 END)   AS billed_hours,
        SUM(CASE WHEN b.status = 'completed' THEN b.net_amount ELSE 0 END)     AS booking_value_eur,
        SUM(CASE WHEN b.status = 'completed' THEN b.cleaner_payout ELSE 0 END) AS cleaner_payout_eur,
        ISNULL(SUM(pay.paid), 0)                                               AS cash_collected_eur
    FROM b
    LEFT JOIN pay ON pay.booking_id = b.booking_id
    GROUP BY b.month_start, b.zone_id
    ORDER BY b.month_start, b.zone_id;
END
GO

/* Bookings by status, month and city.
   Used by: operations weekly review. */
CREATE OR ALTER PROCEDURE rpt.usp_BookingStatusMonthly
    @FromMonth DATE,
    @ToMonth   DATE
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        DATEFROMPARTS(YEAR(bk.scheduled_start), MONTH(bk.scheduled_start), 1) AS month_start,
        z.city,
        bk.status,
        COUNT(*) AS bookings
    FROM ops.bookings bk
    JOIN ops.zones z     ON z.zone_id = bk.zone_id
    JOIN ops.customers c ON c.customer_id = bk.customer_id
    WHERE c.email NOT LIKE '%@ucleany.test%'
      AND bk.scheduled_start >= @FromMonth
      AND bk.scheduled_start <  DATEADD(MONTH, 1, @ToMonth)
    GROUP BY DATEFROMPARTS(YEAR(bk.scheduled_start), MONTH(bk.scheduled_start), 1), z.city, bk.status
    ORDER BY 1, 2, 3;
END
GO

/* Cleaner productivity and quality by month.
   Used by: operations, cleaner bonus calculation. */
CREATE OR ALTER PROCEDURE rpt.usp_CleanerMonthly
    @FromMonth DATE,
    @ToMonth   DATE
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        DATEFROMPARTS(YEAR(bk.scheduled_start), MONTH(bk.scheduled_start), 1) AS month_start,
        bk.cleaner_id,
        COUNT(*)                                       AS completed_bookings,
        SUM(bk.billed_hours)                           AS billed_hours,
        SUM(bk.cleaner_payout)                         AS cleaner_payout_eur,
        COUNT(r.review_id)                             AS reviews,
        CAST(AVG(CAST(r.rating AS DECIMAL(5,2))) AS DECIMAL(5,3)) AS avg_rating
    FROM ops.bookings bk
    JOIN ops.customers c    ON c.customer_id = bk.customer_id
    LEFT JOIN ops.reviews r ON r.booking_id = bk.booking_id
    WHERE bk.status = 'completed'
      AND c.email NOT LIKE '%@ucleany.test%'
      AND bk.scheduled_start >= @FromMonth
      AND bk.scheduled_start <  DATEADD(MONTH, 1, @ToMonth)
    GROUP BY DATEFROMPARTS(YEAR(bk.scheduled_start), MONTH(bk.scheduled_start), 1), bk.cleaner_id
    ORDER BY 1, 2;
END
GO

/* New customers by signup month and acquisition channel.
   Used by: marketing, CAC calculation in the Excel pack. */
CREATE OR ALTER PROCEDURE rpt.usp_NewCustomersMonthly
    @FromMonth DATE,
    @ToMonth   DATE
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        DATEFROMPARTS(YEAR(c.signup_at), MONTH(c.signup_at), 1) AS month_start,
        z.city,
        c.acquisition_channel_id AS channel_id,
        COUNT(DISTINCT c.customer_id) AS new_customers
    FROM ops.customers c
    JOIN ops.zones z ON z.zone_id = c.zone_id
    WHERE c.email NOT LIKE '%@ucleany.test%'
      AND c.signup_at >= @FromMonth
      AND c.signup_at <  DATEADD(MONTH, 1, @ToMonth)
    GROUP BY DATEFROMPARTS(YEAR(c.signup_at), MONTH(c.signup_at), 1), z.city, c.acquisition_channel_id
    ORDER BY 1, 2, 3;
END
GO
