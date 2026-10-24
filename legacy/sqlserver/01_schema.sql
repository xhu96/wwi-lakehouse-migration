-- Ucleany operational database (legacy), SQL Server 2019+.
-- Mirrors the shape of the production schema the BI platform was built on:
-- application tables in [ops], reporting procedures in [rpt].

IF DB_ID('ucleany_ops') IS NULL
    CREATE DATABASE ucleany_ops;
GO
USE ucleany_ops;
GO
IF SCHEMA_ID('ops') IS NULL EXEC('CREATE SCHEMA ops');
GO
IF SCHEMA_ID('rpt') IS NULL EXEC('CREATE SCHEMA rpt');
GO

DROP TABLE IF EXISTS ops.reviews, ops.payments, ops.bookings, ops.marketing_spend,
    ops.customers, ops.cleaners, ops.channels, ops.services, ops.zones;
GO

CREATE TABLE ops.zones (
    zone_id      INT           NOT NULL PRIMARY KEY,
    zone_name    NVARCHAR(60)  NOT NULL,
    city         NVARCHAR(30)  NOT NULL,
    area_type    NVARCHAR(30)  NOT NULL
);

CREATE TABLE ops.services (
    service_id        INT           NOT NULL PRIMARY KEY,
    service_code      VARCHAR(10)   NOT NULL,
    service_name      NVARCHAR(60)  NOT NULL,
    pricing_model     VARCHAR(10)   NOT NULL,   -- hourly | flat
    list_price_eur    DECIMAL(8,2)  NOT NULL,
    min_hours         DECIMAL(4,1)  NOT NULL,
    cleaner_rate_eur  DECIMAL(8,2)  NOT NULL
);

CREATE TABLE ops.channels (
    channel_id    INT           NOT NULL PRIMARY KEY,
    channel_code  VARCHAR(30)   NOT NULL,
    channel_name  NVARCHAR(60)  NOT NULL,
    is_paid       BIT           NOT NULL
);

CREATE TABLE ops.customers (
    customer_id             INT            NOT NULL PRIMARY KEY,
    first_name              NVARCHAR(60)   NULL,
    last_name               NVARCHAR(60)   NULL,
    email                   NVARCHAR(200)  NOT NULL,   -- free text, not unique, not normalised
    phone                   NVARCHAR(40)   NULL,
    segment                 VARCHAR(20)    NOT NULL,   -- household | short_let_host | office
    zone_id                 INT            NOT NULL REFERENCES ops.zones(zone_id),
    city_text               NVARCHAR(40)   NULL,       -- typed by the customer at signup
    acquisition_channel_id  INT            NOT NULL REFERENCES ops.channels(channel_id),
    signup_at               DATETIME2(0)   NOT NULL,   -- UTC
    marketing_opt_in        BIT            NOT NULL,
    modified_at             DATETIME2(0)   NOT NULL    -- UTC
);

CREATE TABLE ops.cleaners (
    cleaner_id             INT            NOT NULL PRIMARY KEY,
    first_name             NVARCHAR(60)   NOT NULL,
    last_name              NVARCHAR(60)   NOT NULL,
    email                  NVARCHAR(200)  NOT NULL,
    phone                  NVARCHAR(40)   NULL,
    home_zone_id           INT            NOT NULL REFERENCES ops.zones(zone_id),
    contract_type          VARCHAR(30)    NOT NULL,
    level                  VARCHAR(10)    NOT NULL,   -- standard | senior | top
    weekly_capacity_hours  INT            NOT NULL,
    onboarded_at           DATETIME2(0)   NOT NULL,   -- UTC
    offboarded_at          DATETIME2(0)   NULL,       -- UTC
    modified_at            DATETIME2(0)   NOT NULL    -- UTC
);

CREATE TABLE ops.bookings (
    booking_id        BIGINT         NOT NULL PRIMARY KEY,
    customer_id       INT            NOT NULL REFERENCES ops.customers(customer_id),
    cleaner_id        INT            NULL REFERENCES ops.cleaners(cleaner_id),
    service_id        INT            NOT NULL REFERENCES ops.services(service_id),
    zone_id           INT            NOT NULL REFERENCES ops.zones(zone_id),
    scheduled_start   DATETIME2(0)   NOT NULL,   -- Europe/Rome local time
    planned_hours     DECIMAL(4,1)   NOT NULL,
    billed_hours      DECIMAL(4,1)   NOT NULL,
    unit_price        DECIMAL(8,2)   NOT NULL,
    gross_amount      DECIMAL(10,2)  NOT NULL,
    discount_amount   DECIMAL(10,2)  NOT NULL,
    net_amount        DECIMAL(10,2)  NOT NULL,
    cancellation_fee  DECIMAL(10,2)  NOT NULL,
    cleaner_payout    DECIMAL(10,2)  NOT NULL,
    status            VARCHAR(30)    NOT NULL,
    recurrence        VARCHAR(20)    NOT NULL,
    promo_code        VARCHAR(20)    NULL,
    created_at        DATETIME2(0)   NOT NULL,   -- UTC
    cancelled_at      DATETIME2(0)   NULL,       -- UTC
    completed_at      DATETIME2(0)   NULL,       -- UTC
    modified_at       DATETIME2(0)   NOT NULL    -- UTC
);
CREATE INDEX ix_bookings_scheduled ON ops.bookings(scheduled_start) INCLUDE (status, zone_id, cleaner_id);

CREATE TABLE ops.payments (
    payment_id       BIGINT         NOT NULL PRIMARY KEY,
    booking_id       BIGINT         NOT NULL REFERENCES ops.bookings(booking_id),
    payment_type     VARCHAR(20)    NOT NULL,   -- charge | refund | cancellation_fee
    amount           DECIMAL(10,2)  NOT NULL,   -- refunds are negative
    currency         CHAR(3)        NOT NULL,
    status           VARCHAR(20)    NOT NULL,   -- succeeded | failed
    provider         VARCHAR(20)    NOT NULL,
    provider_txn_id  VARCHAR(40)    NOT NULL,   -- not unique: webhook retries insert twice
    created_at       DATETIME2(0)   NOT NULL    -- UTC
);
CREATE INDEX ix_payments_booking ON ops.payments(booking_id);

CREATE TABLE ops.reviews (
    review_id    BIGINT          NOT NULL PRIMARY KEY,
    booking_id   BIGINT          NOT NULL REFERENCES ops.bookings(booking_id),
    customer_id  INT             NOT NULL,
    cleaner_id   INT             NOT NULL,
    rating       TINYINT         NOT NULL,   -- no CHECK constraint: the 2023 app accepted 0 and 6
    comment      NVARCHAR(400)   NULL,
    created_at   DATETIME2(0)    NOT NULL    -- UTC
);

CREATE TABLE ops.marketing_spend (
    month_start  DATE           NOT NULL,
    city         NVARCHAR(30)   NOT NULL,
    channel_id   INT            NOT NULL REFERENCES ops.channels(channel_id),
    spend_eur    DECIMAL(12,2)  NOT NULL,
    CONSTRAINT pk_marketing_spend PRIMARY KEY (month_start, city, channel_id)
);
GO
