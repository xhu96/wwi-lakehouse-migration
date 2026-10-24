"""SQL models, shared by the Databricks pipeline and local runs.

Models reference tables as ``{catalog}.<schema>.<table>``; ``render`` fills in
the catalog (``spark_catalog`` locally, the Unity Catalog catalog on Databricks).
"""

from __future__ import annotations

from importlib import resources

# Build order: a model may only reference models listed before it.
SILVER_MODELS = ["customer_identity", "reviews_quarantine"]
GOLD_MODELS = [
    "dim_date",
    "dim_zone",
    "dim_service",
    "dim_channel",
    "dim_customer",
    "dim_cleaner",
    "fct_bookings",
    "fct_payments",
    "fct_reviews",
    "fct_marketing_spend",
    "agg_kpi_monthly",
    "agg_cleaner_monthly",
    "agg_customer_cohorts",
]


def read(layer: str, name: str) -> str:
    return resources.files(__package__).joinpath(layer, f"{name}.sql").read_text()


def render(layer: str, name: str, **params: str) -> str:
    sql = read(layer, name)
    for key, value in params.items():
        sql = sql.replace("{" + key + "}", value)
    return sql
