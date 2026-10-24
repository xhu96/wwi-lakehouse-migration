"""Run the whole lakehouse on local Spark: landing -> bronze -> silver -> gold.

Databricks applies changes with AUTO CDC. Locally the same semantics are
emulated with window functions (``apply_scd1`` and ``apply_scd2``), so CI can
build gold and reconcile it against the legacy reports without a workspace.
"""

from __future__ import annotations

from pathlib import Path

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F

from . import reconcile, sql
from .transforms.silver import CDC_META, CDC_TABLES

LOCAL_CATALOG = "spark_catalog"


def spark_session(warehouse: str) -> SparkSession:
    return (
        SparkSession.builder.master("local[2]")
        .appName("ucleany-local")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.warehouse.dir", str(Path(warehouse).resolve()))
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.ansi.enabled", "true")
        .getOrCreate()
    )


def apply_scd1(changes: DataFrame, keys: list[str]) -> DataFrame:
    """Latest version per key; keys whose latest change is a delete disappear."""
    w = Window.partitionBy(*keys).orderBy(F.col("_commit_ts").desc())
    latest = changes.withColumn("_rn", F.row_number().over(w)).filter("_rn = 1")
    return latest.filter(F.col("_op") != "DELETE").drop("_rn", *CDC_META)


def apply_scd2(changes: DataFrame, keys: list[str]) -> DataFrame:
    """One row per version with __START_AT / __END_AT, as AUTO CDC SCD type 2 stores it."""
    w = Window.partitionBy(*keys).orderBy("_commit_ts")
    versions = changes.withColumn("__START_AT", F.col("_commit_ts")).withColumn("__END_AT", F.lead("_commit_ts").over(w))
    return versions.filter(F.col("_op") != "DELETE").drop(*CDC_META)


def check_fail_rules(df: DataFrame, rules: dict[str, str], table: str) -> None:
    for name, rule in rules.items():
        bad = df.filter(f"NOT ({rule})").count()
        if bad:
            raise ValueError(f"{table}: {bad} rows violate {name} ({rule})")


def build_silver(spark: SparkSession, landing: str) -> dict[str, int]:
    spark.sql("CREATE DATABASE IF NOT EXISTS silver")
    counts = {}
    for t in CDC_TABLES:
        raw = spark.read.parquet(str(Path(landing) / t.name))
        clean = t.clean(raw)
        check_fail_rules(clean, t.fail, t.name)
        applied = apply_scd2(clean, t.keys) if t.scd_type == 2 else apply_scd1(clean, t.keys)
        applied.write.mode("overwrite").saveAsTable(f"silver.{t.name}")
        counts[f"silver.{t.name}"] = spark.table(f"silver.{t.name}").count()
    for name in sql.SILVER_MODELS:
        spark.sql(sql.render("silver", name, catalog=LOCAL_CATALOG)).write.mode("overwrite").saveAsTable(f"silver.{name}")
        counts[f"silver.{name}"] = spark.table(f"silver.{name}").count()
    return counts


def build_gold(spark: SparkSession) -> dict[str, int]:
    spark.sql("CREATE DATABASE IF NOT EXISTS gold")
    counts = {}
    for name in sql.GOLD_MODELS:
        spark.sql(sql.render("gold", name, catalog=LOCAL_CATALOG)).write.mode("overwrite").saveAsTable(f"gold.{name}")
        counts[f"gold.{name}"] = spark.table(f"gold.{name}").count()
    return counts


def run(landing: str, snapshots: str, warehouse: str, report_path: str | None = None) -> bool:
    spark = spark_session(warehouse)
    for name, n in {**build_silver(spark, landing), **build_gold(spark)}.items():
        print(f"{name:<32} {n:>9,}")

    results = reconcile.reconcile_all(spark, LOCAL_CATALOG, snapshots).cache()
    summary = reconcile.summarise(results)
    print(summary.to_string(index=False))
    breaks = results.filter("status = 'BREAK'")
    n_breaks = breaks.count()
    if n_breaks:
        breaks.show(20, truncate=False)
    if report_path:
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(report_path).write_text(reconcile.markdown_report(summary))
    return n_breaks == 0
