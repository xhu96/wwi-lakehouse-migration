"""Create the Unity Catalog objects the lakehouse needs. Safe to run repeatedly."""

import argparse

from pyspark.sql import SparkSession

p = argparse.ArgumentParser()
p.add_argument("--catalog", required=True)
args = p.parse_args()

spark = SparkSession.builder.getOrCreate()
c = args.catalog

statements = [
    f"CREATE CATALOG IF NOT EXISTS {c} COMMENT 'Ucleany BI platform'",
    f"CREATE SCHEMA IF NOT EXISTS {c}.landing COMMENT 'CDC extracts from the SQL Server operational database'",
    f"CREATE VOLUME IF NOT EXISTS {c}.landing.cdc COMMENT 'Parquet change files, one folder per source table'",
    f"CREATE SCHEMA IF NOT EXISTS {c}.bronze COMMENT 'Raw change rows, append only'",
    f"CREATE SCHEMA IF NOT EXISTS {c}.silver COMMENT 'Cleaned, deduplicated, history-tracked. Contains personal data'",
    f"CREATE SCHEMA IF NOT EXISTS {c}.gold COMMENT 'Star schema and KPIs for Power BI. No direct identifiers'",
]
for stmt in statements:
    if stmt.startswith("CREATE CATALOG"):
        try:
            spark.sql(stmt)
        except Exception as exc:  # the catalog may exist already, or the user may not be allowed to create one
            if spark.sql(f"SHOW CATALOGS LIKE '{c}'").count() == 0:
                raise RuntimeError(
                    f"Catalog {c} does not exist and could not be created ({exc}). "
                    "Create it in Catalog Explorer, or deploy with --var catalog=<an existing catalog>."
                ) from exc
        continue
    spark.sql(stmt)
    print(stmt)
