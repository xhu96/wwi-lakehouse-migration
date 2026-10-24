# Bronze: the CDC extract of the SQL Server tables, appended as it lands.
# Auto Loader picks up each new batch file from the landing volume exactly once.

import sys

sys.path.append(spark.conf.get("ucleany.src_path"))  # noqa: F821 - `spark` is provided by the pipeline runtime

import dlt  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402

from ucleany.transforms.silver import CDC_TABLES  # noqa: E402

CATALOG = spark.conf.get("ucleany.catalog")  # noqa: F821
LANDING = spark.conf.get("ucleany.landing_path")  # noqa: F821


def bronze_table(name: str) -> None:
    @dlt.table(
        name=f"{CATALOG}.bronze.{name}",
        comment=f"Raw change rows from ops.{name} (SQL Server), append only. One row per insert, update or delete.",
        table_properties={"quality": "bronze", "source_system": "sqlserver.ucleany_ops"},
    )
    def _bronze():
        return (
            spark.readStream.format("cloudFiles")  # noqa: F821
            .option("cloudFiles.format", "parquet")
            .option("cloudFiles.schemaEvolutionMode", "addNewColumns")
            .load(f"{LANDING}/{name}")
            .select(
                "*",
                F.col("_metadata.file_path").alias("_source_file"),
                F.current_timestamp().alias("_ingested_at"),
            )
        )


for table in CDC_TABLES:
    bronze_table(table.name)
