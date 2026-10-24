"""Reconcile gold with the legacy SQL Server reports and publish the result.

Writes gold.reconciliation_results (one row per report cell and metric) and
gold.reconciliation_summary, then fails the job if any cell is a BREAK.
"""

import argparse
import sys

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

p = argparse.ArgumentParser()
p.add_argument("--catalog", required=True)
p.add_argument("--src", required=True)
p.add_argument("--snapshots", required=True)
args = p.parse_args()

sys.path.append(args.src)

from ucleany import reconcile  # noqa: E402

spark = SparkSession.builder.getOrCreate()
results = reconcile.reconcile_all(spark, args.catalog, args.snapshots).withColumn("reconciled_at", F.current_timestamp())
results.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{args.catalog}.gold.reconciliation_results")

summary = reconcile.summarise(spark.table(f"{args.catalog}.gold.reconciliation_results"))
spark.createDataFrame(summary).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"{args.catalog}.gold.reconciliation_summary"
)
print(summary.to_string(index=False))

breaks = int(summary["breaks"].sum())
if breaks:
    raise RuntimeError(f"{breaks} reconciliation breaks: see {args.catalog}.gold.reconciliation_results")
