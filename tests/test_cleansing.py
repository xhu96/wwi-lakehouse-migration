import datetime as dt

import pytest
from pyspark.sql import functions as F

from ucleany.transforms import cleansing


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("+39 345 123 4567", "+393451234567"),
        ("3451234567", "+393451234567"),
        ("00393451234567", "+393451234567"),
        ("345-123-4567", "+393451234567"),
        ("+393451234567", "+393451234567"),
        ("06 1234567", None),
        (None, None),
    ],
)
def test_normalize_phone(spark, raw, expected):
    df = spark.createDataFrame([(raw,)], "p string")
    assert df.select(cleansing.normalize_phone(F.col("p"))).first()[0] == expected


@pytest.mark.parametrize(
    "raw, expected",
    [("Roma", "Roma"), ("ROMA", "Roma"), ("Rome", "Roma"), ("Roma (RM)", "Roma"), ("Roma ", "Roma"), ("milan", "Milano")],
)
def test_normalize_city(spark, raw, expected):
    df = spark.createDataFrame([(raw,)], "c string")
    assert df.select(cleansing.normalize_city(F.col("c"))).first()[0] == expected


def test_email_rules(spark):
    df = spark.createDataFrame(
        [(" Giulia.Rossi@Gmail.com ",), ("qa.10003@UCLEANY.TEST",), ("erased+1@privacy.ucleany.invalid",)], "e string"
    )
    rows = df.select(
        cleansing.normalize_email(F.col("e")).alias("email"),
        cleansing.is_test_email(F.col("e")).alias("test"),
        cleansing.is_erased_email(F.col("e")).alias("erased"),
    ).collect()
    assert rows[0]["email"] == "giulia.rossi@gmail.com"
    assert [r["test"] for r in rows] == [False, True, False]
    assert [r["erased"] for r in rows] == [False, False, True]


@pytest.mark.parametrize(
    "local, utc",
    [
        (dt.datetime(2026, 7, 1, 10, 0), dt.datetime(2026, 7, 1, 8, 0)),  # CEST, UTC+2
        (dt.datetime(2026, 12, 1, 10, 0), dt.datetime(2026, 12, 1, 9, 0)),  # CET, UTC+1
        (dt.datetime(2026, 10, 25, 10, 0), dt.datetime(2026, 10, 25, 9, 0)),  # day clocks go back
    ],
)
def test_local_to_utc(spark, local, utc):
    df = spark.createDataFrame([(local,)], "t timestamp_ntz")
    assert df.select(cleansing.local_to_utc(F.col("t"))).first()[0] == utc
