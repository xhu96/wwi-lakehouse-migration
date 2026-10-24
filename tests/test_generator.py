import json

import pandas as pd

from conftest import SNAPSHOTS
from ucleany.synth.generate import ScenarioConfig, fingerprint, generate


def test_generator_is_deterministic(dataset):
    again = generate(ScenarioConfig())
    assert fingerprint(again) == fingerprint(dataset)


def test_fingerprint_matches_legacy_baseline(dataset):
    """The committed SQL Server report snapshots were produced from exactly this data."""
    manifest = json.loads((SNAPSHOTS / "manifest.json").read_text())
    assert manifest["generator"] == ScenarioConfig().__dict__
    assert fingerprint(dataset) == manifest["data_fingerprint"]


def test_rome_only_and_launch_date(dataset):
    zones = dataset.current["zones"]
    bookings = dataset.current["bookings"].merge(zones, on="zone_id")
    assert set(bookings["city"]) == {"Roma"}
    assert dataset.current["customers"]["signup_at"].min() >= pd.Timestamp("2026-05-01")


def test_nothing_after_the_extract(dataset):
    as_of = dataset.config.as_of_ts
    for name, df in dataset.changes.items():
        assert (df["_commit_ts"] <= as_of).all(), name


def test_referential_integrity(dataset):
    c = dataset.current
    assert c["bookings"]["customer_id"].isin(c["customers"]["customer_id"]).all()
    assert c["bookings"]["cleaner_id"].isin(c["cleaners"]["cleaner_id"]).all()
    assert c["bookings"]["zone_id"].isin(c["zones"]["zone_id"]).all()
    assert c["payments"]["booking_id"].isin(c["bookings"]["booking_id"]).all()
    assert c["reviews"]["booking_id"].isin(c["bookings"]["booking_id"]).all()


def test_booking_lifecycle_is_consistent(dataset):
    b = dataset.current["bookings"]
    done = b[b["status"] == "completed"]
    assert done["completed_at"].notna().all()
    assert (done["created_at"] < done["completed_at"]).all()
    assert (b.loc[b["status"] == "confirmed", "completed_at"].isna()).all()
    assert (b["net_amount"] == (b["gross_amount"] - b["discount_amount"]).round(2)).all()
    shares = b["status"].value_counts(normalize=True)
    assert 0.04 < shares["cancelled_by_customer"] < 0.10


def test_emails_unique_except_known_duplicates(dataset):
    cust = dataset.changes["customers"].sort_values("_commit_ts").groupby("customer_id").head(1)
    key = cust["email"].str.strip().str.lower()
    dup_accounts = set(cust.loc[key.duplicated(keep="first"), "customer_id"])
    assert dup_accounts == set(dataset.truth["duplicate_customer_ids"])


def test_defects_are_present(dataset):
    t = dataset.truth
    assert len(t["test_customer_ids"]) == 12
    assert len(t["duplicate_customer_ids"]) > 0
    assert len(t["duplicate_payment_ids"]) > 0
    assert len(t["invalid_review_ids"]) > 0
    assert len(t["deleted_review_ids"]) > 0
