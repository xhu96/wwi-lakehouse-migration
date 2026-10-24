# Gold: the star schema and KPI tables served to Power BI.
# Each model is a materialized view defined by a SQL file in ucleany/sql/gold.

import sys

sys.path.append(spark.conf.get("ucleany.src_path"))  # noqa: F821

import dlt  # noqa: E402

from ucleany import sql  # noqa: E402

CATALOG = spark.conf.get("ucleany.catalog")  # noqa: F821

COMMENTS = {
    "dim_date": "Calendar with Italian public holidays (and 29 June for Rome).",
    "dim_zone": "Service zones.",
    "dim_service": "Service catalogue.",
    "dim_channel": "Acquisition channels.",
    "dim_customer": "Customers, SCD type 2, no direct identifiers. Grain: one row per customer version.",
    "dim_cleaner": "Cleaners, SCD type 2. Grain: one row per cleaner version.",
    "fct_bookings": "Bookings. Grain: one row per booking. Test accounts excluded.",
    "fct_payments": "Payment records with duplicate webhook flag. Grain: one row per payment record.",
    "fct_reviews": "Valid customer reviews. Grain: one row per review.",
    "fct_marketing_spend": "Marketing spend. Grain: month, city, channel.",
    "agg_kpi_monthly": "Monthly business KPIs.",
    "agg_cleaner_monthly": "Cleaner hours, capacity, utilisation and rating by month.",
    "agg_customer_cohorts": "Customer retention by cohort month.",
}


def gold_model(name: str) -> None:
    @dlt.table(name=f"{CATALOG}.gold.{name}", comment=COMMENTS.get(name), table_properties={"quality": "gold"})
    def _model():
        return spark.sql(sql.render("gold", name, catalog=CATALOG))  # noqa: F821


for model in sql.GOLD_MODELS:
    gold_model(model)
