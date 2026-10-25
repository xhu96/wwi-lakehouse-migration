"""Column-level cleansing rules shared by the Databricks pipeline and local runs."""

from __future__ import annotations

from pyspark.sql import Column
from pyspark.sql import functions as F

TEST_EMAIL_DOMAIN = "ucleany.test"
ERASED_EMAIL_PATTERN = "erased+%@privacy.ucleany.invalid"
SOURCE_TIMEZONE = "Europe/Rome"


def normalize_email(col: Column) -> Column:
    return F.lower(F.trim(col))


def email_domain(col: Column) -> Column:
    return F.substring_index(normalize_email(col), "@", -1)


def email_hash(col: Column) -> Column:
    """Pseudonymous key for matching people across accounts without reading the email itself."""
    return F.sha2(normalize_email(col), 256)


def display_name(first: Column, last: Column) -> Column:
    """First name and initial, as the app shows cleaners to customers."""
    return F.concat(first, F.lit(" "), F.substring(last, 1, 1), F.lit("."))


def normalize_phone(col: Column) -> Column:
    """Italian mobile numbers to E.164 (+393xxxxxxxxx); anything else to NULL."""
    digits = F.regexp_replace(col, r"[^0-9]", "")
    national = (
        F.when(digits.startswith("0039") & (F.length(digits) == 14), F.substring(digits, 5, 10))
        .when(digits.startswith("39") & (F.length(digits) == 12), F.substring(digits, 3, 10))
        .otherwise(digits)
    )
    return F.when(national.rlike(r"^3[0-9]{9}$"), F.concat(F.lit("+39"), national))


def normalize_city(col: Column) -> Column:
    key = F.lower(F.trim(F.regexp_replace(col, r"\(.*\)", "")))
    return (
        F.when(key.isin("roma", "rome"), F.lit("Roma")).when(key.isin("milano", "milan"), F.lit("Milano")).otherwise(F.initcap(F.trim(col)))
    )


def is_test_email(col: Column) -> Column:
    return email_domain(col) == F.lit(TEST_EMAIL_DOMAIN)


def is_erased_email(col: Column) -> Column:
    return normalize_email(col).like(ERASED_EMAIL_PATTERN)


def local_to_utc(col: Column, tz: str = SOURCE_TIMEZONE) -> Column:
    """Rome wall-clock time to a UTC instant. Requires spark.sql.session.timeZone=UTC."""
    return F.to_utc_timestamp(col.cast("timestamp"), tz)


def money(col: Column) -> Column:
    return col.cast("decimal(12,2)")
