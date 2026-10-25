"""Bronze change rows to cleaned change rows, ready for AUTO CDC.

Each function takes the bronze change feed of one table (batch or stream) and
returns typed, standardised rows that still carry ``_op`` and ``_commit_ts``.
``CDC_TABLES`` describes how each table is applied downstream: the keys, the
SCD type and the data quality rules. The Databricks pipeline and the local
runner both read it, so the two cannot drift apart.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from .cleansing import (
    display_name,
    email_domain,
    email_hash,
    is_erased_email,
    is_test_email,
    local_to_utc,
    money,
    normalize_city,
    normalize_email,
    normalize_phone,
)

CDC_META = ["_op", "_commit_ts"]
INGEST_META = ["batch", "_ingested_at", "_source_file", "_rescued_data"]

BOOKING_STATUSES = ("confirmed", "completed", "cancelled_by_customer", "cancelled_by_cleaner", "no_show")


def _drop_ingest_meta(df: DataFrame) -> DataFrame:
    return df.drop(*[c for c in INGEST_META if c in df.columns])


def zones(df: DataFrame) -> DataFrame:
    return _drop_ingest_meta(df).select(F.col("zone_id").cast("int"), "zone_name", "city", "area_type", *CDC_META)


def services(df: DataFrame) -> DataFrame:
    return _drop_ingest_meta(df).select(
        F.col("service_id").cast("int"),
        "service_code",
        "service_name",
        "pricing_model",
        money(F.col("list_price_eur")).alias("list_price_eur"),
        F.col("min_hours").cast("decimal(4,1)"),
        money(F.col("cleaner_rate_eur")).alias("cleaner_rate_eur"),
        *CDC_META,
    )


def channels(df: DataFrame) -> DataFrame:
    return _drop_ingest_meta(df).select(
        F.col("channel_id").cast("int"), "channel_code", "channel_name", F.col("is_paid").cast("boolean"), *CDC_META
    )


def customers(df: DataFrame) -> DataFrame:
    df = _drop_ingest_meta(df)
    return df.select(
        F.col("customer_id").cast("int"),
        "first_name",
        "last_name",
        F.col("email").alias("email_raw"),
        normalize_email(F.col("email")).alias("email"),
        email_hash(F.col("email")).alias("email_hash"),
        email_domain(F.col("email")).alias("email_domain"),
        normalize_phone(F.col("phone")).alias("phone_e164"),
        F.col("segment"),
        F.col("zone_id").cast("int"),
        normalize_city(F.col("city_text")).alias("city"),
        F.col("acquisition_channel_id").cast("int"),
        F.col("signup_at").cast("timestamp"),
        F.col("marketing_opt_in").cast("boolean"),
        is_test_email(F.col("email")).alias("is_test_account"),
        is_erased_email(F.col("email")).alias("is_erased"),
        *CDC_META,
    )


def cleaners(df: DataFrame) -> DataFrame:
    df = _drop_ingest_meta(df)
    return df.select(
        F.col("cleaner_id").cast("int"),
        "first_name",
        "last_name",
        display_name(F.col("first_name"), F.col("last_name")).alias("display_name"),
        normalize_email(F.col("email")).alias("email"),
        normalize_phone(F.col("phone")).alias("phone_e164"),
        F.col("home_zone_id").cast("int"),
        "contract_type",
        "level",
        F.col("weekly_capacity_hours").cast("int"),
        F.col("onboarded_at").cast("timestamp"),
        F.col("offboarded_at").cast("timestamp"),
        *CDC_META,
    )


def bookings(df: DataFrame) -> DataFrame:
    df = _drop_ingest_meta(df)
    local = F.col("scheduled_start").cast("timestamp_ntz")
    return df.select(
        F.col("booking_id").cast("bigint"),
        F.col("customer_id").cast("int"),
        F.col("cleaner_id").cast("int"),
        F.col("service_id").cast("int"),
        F.col("zone_id").cast("int"),
        local.alias("scheduled_start_local"),
        local_to_utc(local).alias("scheduled_start_utc"),
        F.to_date(local).alias("service_date"),
        F.col("planned_hours").cast("decimal(4,1)"),
        F.col("billed_hours").cast("decimal(4,1)"),
        money(F.col("unit_price")).alias("unit_price"),
        money(F.col("gross_amount")).alias("gross_amount"),
        money(F.col("discount_amount")).alias("discount_amount"),
        money(F.col("net_amount")).alias("net_amount"),
        money(F.col("cancellation_fee")).alias("cancellation_fee"),
        money(F.col("cleaner_payout")).alias("cleaner_payout"),
        F.lower(F.trim(F.col("status"))).alias("status"),
        "recurrence",
        F.upper(F.trim(F.col("promo_code"))).alias("promo_code"),
        F.col("created_at").cast("timestamp"),
        F.col("cancelled_at").cast("timestamp"),
        F.col("completed_at").cast("timestamp"),
        *CDC_META,
    )


def payments(df: DataFrame) -> DataFrame:
    df = _drop_ingest_meta(df)
    return df.select(
        F.col("payment_id").cast("bigint"),
        F.col("booking_id").cast("bigint"),
        "payment_type",
        money(F.col("amount")).alias("amount"),
        "currency",
        "status",
        "provider",
        "provider_txn_id",
        F.col("created_at").cast("timestamp"),
        *CDC_META,
    )


def reviews(df: DataFrame) -> DataFrame:
    df = _drop_ingest_meta(df)
    return df.select(
        F.col("review_id").cast("bigint"),
        F.col("booking_id").cast("bigint"),
        F.col("customer_id").cast("int"),
        F.col("cleaner_id").cast("int"),
        F.col("rating").cast("int"),
        F.col("rating").between(1, 5).alias("is_valid_rating"),
        "comment",
        F.col("created_at").cast("timestamp"),
        *CDC_META,
    )


def marketing_spend(df: DataFrame) -> DataFrame:
    df = _drop_ingest_meta(df)
    return df.select(
        F.col("month_start").cast("date"),
        "city",
        F.col("channel_id").cast("int"),
        money(F.col("spend_eur")).alias("spend_eur"),
        *CDC_META,
    )


@dataclass(frozen=True)
class CdcTable:
    name: str
    keys: list[str]
    clean: Callable[[DataFrame], DataFrame]
    scd_type: int = 1
    # Rows failing these are kept but counted (pipeline expectation, warn only).
    warn: dict[str, str] = field(default_factory=dict)
    # Rows failing these stop the pipeline update: they mean the extract is broken.
    fail: dict[str, str] = field(default_factory=dict)
    comment: str = ""


CDC_TABLES: list[CdcTable] = [
    CdcTable("zones", ["zone_id"], zones, fail={"zone_id_present": "zone_id IS NOT NULL"}, comment="Service zones of Rome."),
    CdcTable(
        "services",
        ["service_id"],
        services,
        fail={"service_id_present": "service_id IS NOT NULL"},
        comment="Service catalogue and list prices.",
    ),
    CdcTable("channels", ["channel_id"], channels, comment="Customer acquisition channels."),
    CdcTable(
        "customers",
        ["customer_id"],
        customers,
        scd_type=2,
        fail={"customer_id_present": "customer_id IS NOT NULL"},
        warn={"email_parseable": "email LIKE '%_@_%._%'", "phone_parseable": "phone_e164 IS NOT NULL OR is_erased"},
        comment="Customer history (SCD type 2). Contains personal data: restricted.",
    ),
    CdcTable(
        "cleaners",
        ["cleaner_id"],
        cleaners,
        scd_type=2,
        fail={"cleaner_id_present": "cleaner_id IS NOT NULL"},
        warn={"valid_level": "level IN ('standard', 'senior', 'top')"},
        comment="Cleaner history (SCD type 2): level, zone and contract changes. Contains personal data: restricted.",
    ),
    CdcTable(
        "bookings",
        ["booking_id"],
        bookings,
        fail={"booking_id_present": "booking_id IS NOT NULL"},
        warn={
            "known_status": "status IN " + str(BOOKING_STATUSES),
            "non_negative_amounts": "net_amount >= 0 AND cleaner_payout >= 0",
            "plausible_duration": "billed_hours BETWEEN 0.5 AND 12",
            "completed_has_cleaner": "status <> 'completed' OR cleaner_id IS NOT NULL",
        },
        comment="Bookings, current state.",
    ),
    CdcTable(
        "payments",
        ["payment_id"],
        payments,
        fail={"payment_id_present": "payment_id IS NOT NULL"},
        warn={"refund_sign": "payment_type <> 'refund' OR amount < 0", "eur_only": "currency = 'EUR'"},
        comment="Payment provider events, one row per payment record (duplicates still present).",
    ),
    CdcTable(
        "reviews",
        ["review_id"],
        reviews,
        warn={"rating_in_range": "is_valid_rating"},
        comment="Customer reviews; moderation deletes are applied.",
    ),
    CdcTable("marketing_spend", ["month_start", "city", "channel_id"], marketing_spend, comment="Monthly marketing spend by channel."),
]
