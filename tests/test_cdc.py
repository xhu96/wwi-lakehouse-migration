import datetime as dt

from ucleany.local_runner import apply_scd1, apply_scd2

T = dt.datetime


def _changes(spark):
    rows = [
        (1, "standard", "INSERT", T(2026, 5, 1)),
        (1, "senior", "UPDATE", T(2026, 9, 1)),
        (2, "standard", "INSERT", T(2026, 6, 1)),
        (2, "standard", "DELETE", T(2026, 7, 1)),
        (3, "top", "INSERT", T(2026, 8, 1)),
    ]
    return spark.createDataFrame(rows, "id int, level string, _op string, _commit_ts timestamp")


def test_scd1_keeps_latest_and_applies_deletes(spark):
    out = {r["id"]: r["level"] for r in apply_scd1(_changes(spark), ["id"]).collect()}
    assert out == {1: "senior", 3: "top"}


def test_scd2_versions(spark):
    out = apply_scd2(_changes(spark), ["id"]).orderBy("id", "__START_AT").collect()
    assert [(r["id"], r["level"], r["__START_AT"], r["__END_AT"]) for r in out] == [
        (1, "standard", T(2026, 5, 1), T(2026, 9, 1)),
        (1, "senior", T(2026, 9, 1), None),
        (2, "standard", T(2026, 6, 1), T(2026, 7, 1)),
        (3, "top", T(2026, 8, 1), None),
    ]
