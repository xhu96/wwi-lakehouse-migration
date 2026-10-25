"""Landing -> silver -> gold on local Spark, then reconcile with the SQL Server baseline."""

import pytest

from conftest import ROOT, SNAPSHOTS
from ucleany import governance, reconcile, sql
from ucleany.local_runner import LOCAL_CATALOG, build_gold, build_silver
from ucleany.synth.landing import write_landing


@pytest.fixture(scope="module")
def lakehouse(spark, dataset, tmp_path_factory):
    landing = tmp_path_factory.mktemp("landing")
    write_landing(dataset, landing)
    build_silver(spark, str(landing))
    build_gold(spark)
    return spark


def test_reconciliation_has_no_breaks(lakehouse):
    results = reconcile.reconcile_all(lakehouse, LOCAL_CATALOG, SNAPSHOTS)
    breaks = results.filter("status = 'BREAK'")
    assert breaks.count() == 0, breaks.limit(10).toPandas().to_string()


def test_known_rule_changes_are_the_only_differences(lakehouse):
    results = reconcile.reconcile_all(lakehouse, LOCAL_CATALOG, SNAPSHOTS)
    explained = {(r["report"], r["metric"]) for r in results.filter("status = 'EXPLAINED'").select("report", "metric").distinct().collect()}
    assert explained == {
        ("monthly_revenue_by_zone", "cash_collected_eur"),
        ("cleaner_monthly", "reviews"),
        ("cleaner_monthly", "avg_rating"),
        ("new_customers_monthly", "new_customers"),
    }


def test_duplicate_accounts_detected_exactly(lakehouse, dataset):
    found = {r[0] for r in lakehouse.sql("SELECT customer_id FROM silver.customer_identity WHERE is_duplicate_account").collect()}
    assert found == set(dataset.truth["duplicate_customer_ids"])


def test_duplicate_payments_flagged_exactly(lakehouse, dataset):
    found = {r[0] for r in lakehouse.sql("SELECT payment_id FROM gold.fct_payments WHERE is_duplicate").collect()}
    expected = set(dataset.truth["duplicate_payment_ids"])
    test_bookings = set(
        dataset.current["bookings"].loc[dataset.current["bookings"]["customer_id"].isin(dataset.truth["test_customer_ids"]), "booking_id"]
    )
    pay = dataset.current["payments"]
    expected -= set(pay.loc[pay["booking_id"].isin(test_bookings), "payment_id"])
    assert found == expected


def test_invalid_ratings_quarantined(lakehouse, dataset):
    found = {r[0] for r in lakehouse.sql("SELECT review_id FROM silver.reviews_quarantine").collect()}
    assert found == set(dataset.truth["invalid_review_ids"])
    assert lakehouse.sql("SELECT count(*) FROM gold.fct_reviews WHERE rating NOT BETWEEN 1 AND 5").first()[0] == 0


def test_gold_has_no_test_accounts_or_personal_data(lakehouse, dataset):
    test_ids = ",".join(str(i) for i in dataset.truth["test_customer_ids"])
    assert lakehouse.sql(f"SELECT count(*) FROM gold.fct_bookings WHERE customer_id IN ({test_ids})").first()[0] == 0
    personal = governance.personal_columns(governance.load_policy(ROOT / "governance" / "policy.yml"))
    for model in sql.GOLD_MODELS:
        assert not set(lakehouse.table(f"gold.{model}").columns) & personal, model


def test_policy_covers_real_columns(lakehouse, dataset):
    """Every column the policy tags or masks exists, so a rename cannot silently drop a mask."""
    policy = governance.load_policy(ROOT / "governance" / "policy.yml")
    for table, columns in policy["personal_data"]["columns"].items():
        layer, name = table.split(".")
        actual = set(dataset.changes[name].columns) if layer == "bronze" else set(lakehouse.table(table).columns)
        assert set(columns) <= actual, f"{table}: {set(columns) - actual}"
    for table, column in policy["row_filters"]["tables"].items():
        assert column in lakehouse.table(table).columns


def test_every_fact_row_finds_its_dimension_versions(lakehouse):
    missing = lakehouse.sql(
        "SELECT count(*) FROM gold.fct_bookings WHERE customer_sk IS NULL OR (cleaner_id IS NOT NULL AND cleaner_sk IS NULL)"
    ).first()[0]
    assert missing == 0


def test_kpis_are_plausible(lakehouse):
    k = lakehouse.sql("SELECT * FROM gold.agg_kpi_monthly ORDER BY month_start").toPandas()
    assert list(k["month_start"].astype(str)) == ["2026-05-01", "2026-06-01", "2026-07-01", "2026-08-01", "2026-09-01", "2026-10-01"]
    assert k["take_rate"].between(0.25, 0.40).all()
    assert k["avg_rating"].between(4.0, 5.0).all()
