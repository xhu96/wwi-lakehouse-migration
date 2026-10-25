"""The access policy: consistent, complete for personal data, and rendered to the SQL we expect."""

import copy

import pytest

from conftest import ROOT
from ucleany import governance

POLICY_PATH = ROOT / "governance" / "policy.yml"


@pytest.fixture(scope="module")
def policy():
    return governance.load_policy(POLICY_PATH)


@pytest.fixture(scope="module")
def statements(policy):
    types = {"silver.customers": "STREAMING_TABLE", "gold.fct_bookings": "MATERIALIZED_VIEW"}
    return governance.plan(policy, "ucleany_dev", types)


def by_kind(statements, kind):
    return [s.sql for s in statements if s.kind == kind]


def test_policy_rejects_unknown_groups(policy):
    broken = copy.deepcopy(policy)
    broken["grants"]["schemas"]["gold"]["interns"] = ["SELECT"]
    with pytest.raises(ValueError, match="interns"):
        governance.validate(broken)


def test_raw_layers_are_closed_to_everyone_but_engineers(policy):
    for schema in ("landing", "bronze"):
        assert schema not in policy["grants"]["schemas"]
    catalog = policy["grants"]["catalog"]
    assert catalog["engineers"] == ["ALL PRIVILEGES"]
    assert all(privileges == ["USE CATALOG"] for key, privileges in catalog.items() if key != "engineers")


def test_contact_details_are_masked_in_silver(policy):
    silver = {t: cols for t, cols in policy["personal_data"]["columns"].items() if t.startswith("silver.")}
    for table, columns in silver.items():
        for column, spec in columns.items():
            if spec["pii"] in ("name", "email", "phone", "free_text"):
                assert "mask" in spec, f"{table}.{column} is personal data readable by analysts without a mask"


def test_masked_readers_never_include_analysts(policy):
    assert "analysts" not in policy["personal_data"]["unmasked_for"]
    assert "zone_managers" not in policy["row_filters"]["all_zones"]


def test_streaming_tables_and_views_get_the_right_alter_keyword(statements):
    masks = by_kind(statements, "mask")
    assert "ALTER STREAMING TABLE ucleany_dev.silver.customers ALTER COLUMN email SET MASK ucleany_dev.governance.mask_email" in masks
    filters = by_kind(statements, "row_filter")
    assert "ALTER MATERIALIZED VIEW ucleany_dev.gold.fct_bookings SET ROW FILTER ucleany_dev.governance.zone_filter ON (zone_id)" in filters


def test_functions_and_tables_exist_before_they_are_used(statements):
    kinds = [s.kind for s in statements]
    assert kinds.index("mask") > max(i for i, k in enumerate(kinds) if k == "function")
    assert kinds.index("function") > max(i for i, k in enumerate(kinds) if k == "setup")


def test_zone_filter_reads_the_entitlement_table(statements, policy):
    zone_filter = next(s for s in by_kind(statements, "function") if "zone_filter" in s)
    assert "ucleany_dev.governance.zone_access" in zone_filter
    for key in policy["row_filters"]["all_zones"]:
        assert f"is_account_group_member('{policy['groups'][key]}')" in zone_filter
    access = next(s for s in by_kind(statements, "setup") if "zone_access" in s)
    assert "('manager.centro@ucleany.example', 101)" in access


def test_every_zone_has_at_most_one_manager(policy):
    zones = [z for entry in policy["zone_access"] for z in entry["zones"]]
    assert len(zones) == len(set(zones))
    assert set(zones) == set(range(101, 117))  # every Rome zone is covered


def test_grants_carry_their_group_so_missing_groups_can_be_skipped(statements):
    grants = [s for s in statements if s.kind == "grant"]
    assert grants and all(s.principal and f"`{s.principal}`" in s.sql for s in grants)
    assert "GRANT USE SCHEMA, SELECT ON SCHEMA ucleany_dev.gold TO `ucleany-analysts`" in [s.sql for s in grants]


def test_drift_revokes_only_extra_grants_to_managed_groups(policy):
    current = governance.expected_privileges(policy) | {
        ("bronze", "ucleany-analysts", "SELECT"),  # granted by hand in Catalog Explorer
        ("gold", "someone@ucleany.example", "SELECT"),  # not a policy group: left alone
    }
    revokes = [s.sql for s in governance.drift(policy, "ucleany_dev", current)]
    assert revokes == ["REVOKE SELECT ON SCHEMA ucleany_dev.bronze FROM `ucleany-analysts`"]
