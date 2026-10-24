# Silver: cleaned rows, changes applied with AUTO CDC.
# SCD type 1 keeps the current state; customers and cleaners keep full history (SCD type 2).

import sys

sys.path.append(spark.conf.get("ucleany.src_path"))  # noqa: F821

import dlt  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402

from ucleany import sql  # noqa: E402
from ucleany.transforms.silver import CDC_META, CDC_TABLES, CdcTable  # noqa: E402

CATALOG = spark.conf.get("ucleany.catalog")  # noqa: F821

# create_auto_cdc_flow is the current name of apply_changes; support both runtimes.
create_cdc_flow = getattr(dlt, "create_auto_cdc_flow", None) or dlt.apply_changes


def silver_table(t: CdcTable) -> None:
    view_name = f"{t.name}_changes_clean"

    def changes():
        return t.clean(spark.readStream.table(f"{CATALOG}.bronze.{t.name}"))  # noqa: F821

    fn = changes
    if t.warn:
        fn = dlt.expect_all(t.warn)(fn)
    if t.fail:
        fn = dlt.expect_all_or_fail(t.fail)(fn)
    dlt.view(name=view_name, comment=f"Cleaned change rows of {t.name}.")(fn)

    dlt.create_streaming_table(
        name=f"{CATALOG}.silver.{t.name}",
        comment=t.comment,
        table_properties={"quality": "silver"},
    )
    create_cdc_flow(
        target=f"{CATALOG}.silver.{t.name}",
        source=view_name,
        keys=t.keys,
        sequence_by=F.col("_commit_ts"),
        apply_as_deletes=F.expr("_op = 'DELETE'"),
        except_column_list=CDC_META,
        stored_as_scd_type=t.scd_type,
    )


def silver_model(name: str) -> None:
    @dlt.table(name=f"{CATALOG}.silver.{name}", table_properties={"quality": "silver"})
    def _model():
        return spark.sql(sql.render("silver", name, catalog=CATALOG))  # noqa: F821


for table in CDC_TABLES:
    silver_table(table)

for model in sql.SILVER_MODELS:
    silver_model(model)
