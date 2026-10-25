"""Unity Catalog access policy as code.

load_policy() reads governance/policy.yml, plan() turns it into SQL statements and
apply() runs them on a workspace. plan() and drift() are pure functions, so the
tests check the policy and the generated SQL without a workspace.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

SCHEMAS = ["landing", "bronze", "silver", "gold", "governance"]

# Mask bodies by data class. `value` is the column value; masked readers see a hint, never the data.
MASK_EXPRESSIONS = {
    "email": "concat(left(value, 1), '***@', substring_index(value, '@', -1))",
    "phone": "concat(left(value, 3), ' *** *** ', right(value, 2))",
    "name": "concat(left(value, 1), '.')",
    "free_text": "'[redacted]'",
}

# information_schema.tables.table_type -> keyword ALTER needs for that object.
ALTER_KEYWORD = {"STREAMING_TABLE": "STREAMING TABLE", "MATERIALIZED_VIEW": "MATERIALIZED VIEW"}


@dataclass(frozen=True)
class Statement:
    kind: str  # setup | function | tag | mask | row_filter | grant | revoke
    sql: str
    principal: str | None = None  # the group the statement needs to exist


def load_policy(path: str | Path) -> dict:
    policy = yaml.safe_load(Path(path).read_text())
    validate(policy)
    return policy


def validate(policy: dict) -> None:
    """Fail early on references to groups, schemas or mask classes that do not exist."""
    groups = policy["groups"]
    used = set(policy["grants"]["catalog"]) | set(policy["personal_data"]["unmasked_for"]) | set(policy["row_filters"]["all_zones"])
    for grants in policy["grants"]["schemas"].values():
        used |= set(grants)
    unknown = used - set(groups)
    if unknown:
        raise ValueError(f"policy refers to undefined groups: {sorted(unknown)}")
    for schema in list(policy["grants"]["schemas"]) + list(policy["schema_tags"]):
        if schema not in SCHEMAS:
            raise ValueError(f"unknown schema {schema!r}")
    for table, columns in policy["personal_data"]["columns"].items():
        for column, spec in columns.items():
            if "mask" in spec and spec["mask"] not in MASK_EXPRESSIONS:
                raise ValueError(f"{table}.{column}: unknown mask {spec['mask']!r}")
    for zone in policy["zone_access"]:
        if not zone["zones"]:
            raise ValueError(f"{zone['user']} has no zones")


def personal_columns(policy: dict) -> set[str]:
    return {column for columns in policy["personal_data"]["columns"].values() for column in columns}


def _members(policy: dict, keys: list[str]) -> str:
    return " OR ".join(f"is_account_group_member('{policy['groups'][k]}')" for k in keys)


def _tags(tags: dict) -> str:
    return ", ".join(f"'{k}' = '{v}'" for k, v in tags.items())


def _alter(table_types: dict[str, str], catalog: str, table: str) -> str:
    return f"ALTER {ALTER_KEYWORD.get(table_types.get(table, ''), 'TABLE')} {catalog}.{table}"


def plan(policy: dict, catalog: str, table_types: dict[str, str] | None = None) -> list[Statement]:
    """Every statement needed to bring the catalog in line with the policy, in order.

    table_types maps "schema.table" to its information_schema table_type, so that
    streaming tables and materialized views get the ALTER keyword they need.
    """
    table_types = table_types or {}
    c, gov = catalog, f"{catalog}.governance"
    out = [Statement("setup", f"CREATE SCHEMA IF NOT EXISTS {gov} COMMENT 'Access policy objects, generated from governance/policy.yml'")]

    rows = ", ".join(f"('{z['user'].lower()}', {zone})" for z in policy["zone_access"] for zone in z["zones"])
    out.append(
        Statement(
            "setup",
            f"CREATE OR REPLACE TABLE {gov}.zone_access COMMENT 'Zones each zone manager may see. Drives the gold row filter and Power BI RLS' "
            f"AS SELECT * FROM VALUES {rows} AS t(user_email, zone_id)",
        )
    )

    unmasked = _members(policy, policy["personal_data"]["unmasked_for"])
    for cls, expression in MASK_EXPRESSIONS.items():
        out.append(
            Statement(
                "function",
                f"CREATE OR REPLACE FUNCTION {gov}.mask_{cls}(value STRING) RETURNS STRING "
                f"COMMENT 'Column mask for {cls} data, see governance/policy.yml' "
                f"RETURN CASE WHEN value IS NULL THEN NULL WHEN {unmasked} THEN value ELSE {expression} END",
            )
        )
    out.append(
        Statement(
            "function",
            f"CREATE OR REPLACE FUNCTION {gov}.zone_filter(row_zone_id INT) RETURNS BOOLEAN "
            "COMMENT 'Row filter for gold facts: zone managers see only their zones, see governance/policy.yml' "
            f"RETURN {_members(policy, policy['row_filters']['all_zones'])} "
            f"OR EXISTS (SELECT 1 FROM {gov}.zone_access a WHERE a.zone_id = row_zone_id AND a.user_email = lower(current_user()))",
        )
    )

    for schema, tags in policy["schema_tags"].items():
        out.append(Statement("tag", f"ALTER SCHEMA {c}.{schema} SET TAGS ({_tags(tags)})"))
    for table, columns in policy["personal_data"]["columns"].items():
        alter = _alter(table_types, c, table)
        out.append(Statement("tag", f"{alter} SET TAGS ('contains_pii' = 'true')"))
        for column, spec in columns.items():
            out.append(Statement("tag", f"{alter} ALTER COLUMN {column} SET TAGS ('pii' = '{spec['pii']}')"))
    for table, columns in policy["personal_data"]["columns"].items():
        for column, spec in columns.items():
            if "mask" in spec:
                out.append(Statement("mask", f"{_alter(table_types, c, table)} ALTER COLUMN {column} SET MASK {gov}.mask_{spec['mask']}"))
    for table, column in policy["row_filters"]["tables"].items():
        out.append(Statement("row_filter", f"{_alter(table_types, c, table)} SET ROW FILTER {gov}.zone_filter ON ({column})"))

    for key, privileges in policy["grants"]["catalog"].items():
        group = policy["groups"][key]
        out.append(Statement("grant", f"GRANT {', '.join(privileges)} ON CATALOG {c} TO `{group}`", group))
    for schema, grants in policy["grants"]["schemas"].items():
        for key, privileges in grants.items():
            group = policy["groups"][key]
            out.append(Statement("grant", f"GRANT {', '.join(privileges)} ON SCHEMA {c}.{schema} TO `{group}`", group))
    return out


def expected_privileges(policy: dict) -> set[tuple[str, str, str]]:
    """(securable, group, privilege) for every grant in the policy; securable is '' for the catalog."""
    out = {("", policy["groups"][k], p) for k, privileges in policy["grants"]["catalog"].items() for p in privileges}
    for schema, grants in policy["grants"]["schemas"].items():
        out |= {(schema, policy["groups"][k], p) for k, privileges in grants.items() for p in privileges}
    return out


def drift(policy: dict, catalog: str, current: set[tuple[str, str, str]]) -> list[Statement]:
    """REVOKE statements for direct grants to policy groups that the policy does not contain.

    current holds (securable, group, privilege) rows from information_schema. Groups
    the policy does not manage are left alone.
    """
    managed = set(policy["groups"].values())
    out = []
    for securable, group, privilege in sorted(current - expected_privileges(policy)):
        if group not in managed:
            continue
        target = f"CATALOG {catalog}" if not securable else f"SCHEMA {catalog}.{securable}"
        out.append(Statement("revoke", f"REVOKE {privilege} ON {target} FROM `{group}`", group))
    return out


def _is_missing_principal(exc: Exception) -> bool:
    text = str(exc).upper()
    return "PRINCIPAL_DOES_NOT_EXIST" in text or ("PRINCIPAL" in text and "NOT EXIST" in text)


def apply(spark, policy: dict, catalog: str, strict: bool = False) -> dict[str, int]:  # pragma: no cover - needs a workspace
    """Apply the policy. Returns counts by outcome; raises if anything failed.

    Grants to groups that do not exist yet are skipped with a warning, unless strict.
    Row filters are only set when the identity running the job is in an all_zones
    group: otherwise the filter would hide rows from the pipeline itself.
    """
    types = {
        f"{r.table_schema}.{r.table_name}": r.table_type
        for r in spark.sql(f"SELECT table_schema, table_name, table_type FROM {catalog}.information_schema.tables").collect()
    }
    statements = plan(policy, catalog, types)
    runner_sees_all = spark.sql(f"SELECT {_members(policy, policy['row_filters']['all_zones'])}").first()[0]

    counts = {"applied": 0, "skipped": 0, "failed": 0}
    failures = []

    def run(stmt: Statement) -> None:
        if stmt.kind == "row_filter" and not runner_sees_all:
            msg = "the job identity is not in an all_zones group; add it before enabling row filters"
            if strict:
                failures.append(f"{stmt.sql}: {msg}")
                counts["failed"] += 1
            else:
                print(f"SKIP  {stmt.sql}  ({msg})")
                counts["skipped"] += 1
            return
        try:
            spark.sql(stmt.sql)
            print(f"OK    {stmt.sql[:160]}")
            counts["applied"] += 1
        except Exception as exc:
            if stmt.principal and _is_missing_principal(exc) and not strict:
                print(f"SKIP  {stmt.sql}  (group {stmt.principal} does not exist in this workspace)")
                counts["skipped"] += 1
            else:
                failures.append(f"{stmt.sql}: {exc}")
                counts["failed"] += 1

    for stmt in statements:
        run(stmt)

    groups = ", ".join(f"'{g}'" for g in policy["groups"].values())
    try:
        current = {
            ("", r.grantee, r.privilege_type.replace("_", " "))
            for r in spark.sql(
                f"SELECT grantee, privilege_type FROM {catalog}.information_schema.catalog_privileges "
                f"WHERE grantee IN ({groups}) AND inherited_from = 'NONE'"
            ).collect()
        } | {
            (r.schema_name, r.grantee, r.privilege_type.replace("_", " "))
            for r in spark.sql(
                f"SELECT schema_name, grantee, privilege_type FROM {catalog}.information_schema.schema_privileges "
                f"WHERE grantee IN ({groups}) AND inherited_from = 'NONE'"
            ).collect()
        }
    except Exception as exc:
        if strict:
            raise
        print(f"SKIP  drift check ({exc})")
        current = set()
    for stmt in drift(policy, catalog, current):
        run(stmt)

    print(counts)
    if failures:
        raise RuntimeError("governance policy not fully applied:\n" + "\n".join(failures))
    return counts
