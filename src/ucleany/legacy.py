"""Build the legacy SQL Server database and export its report outputs.

Used locally (Docker) and in CI (SQL Server service container) to produce the
baseline the lakehouse is reconciled against.
"""

from __future__ import annotations

import csv
import dataclasses
import datetime as dt
import json
import math
import re
from decimal import Decimal
from pathlib import Path

import pandas as pd

LOAD_ORDER = ["zones", "services", "channels", "customers", "cleaners", "bookings", "payments", "reviews", "marketing_spend"]

COLUMNS = {
    "zones": ["zone_id", "zone_name", "city", "area_type"],
    "services": ["service_id", "service_code", "service_name", "pricing_model", "list_price_eur", "min_hours", "cleaner_rate_eur"],
    "channels": ["channel_id", "channel_code", "channel_name", "is_paid"],
    "customers": [
        "customer_id",
        "first_name",
        "last_name",
        "email",
        "phone",
        "segment",
        "zone_id",
        "city_text",
        "acquisition_channel_id",
        "signup_at",
        "marketing_opt_in",
        "modified_at",
    ],
    "cleaners": [
        "cleaner_id",
        "first_name",
        "last_name",
        "email",
        "phone",
        "home_zone_id",
        "contract_type",
        "level",
        "weekly_capacity_hours",
        "onboarded_at",
        "offboarded_at",
        "modified_at",
    ],
    "bookings": [
        "booking_id",
        "customer_id",
        "cleaner_id",
        "service_id",
        "zone_id",
        "scheduled_start",
        "planned_hours",
        "billed_hours",
        "unit_price",
        "gross_amount",
        "discount_amount",
        "net_amount",
        "cancellation_fee",
        "cleaner_payout",
        "status",
        "recurrence",
        "promo_code",
        "created_at",
        "cancelled_at",
        "completed_at",
        "modified_at",
    ],
    "payments": ["payment_id", "booking_id", "payment_type", "amount", "currency", "status", "provider", "provider_txn_id", "created_at"],
    "reviews": ["review_id", "booking_id", "customer_id", "cleaner_id", "rating", "comment", "created_at"],
    "marketing_spend": ["month_start", "city", "channel_id", "spend_eur"],
}

REPORTS = {
    "monthly_revenue_by_zone": "rpt.usp_MonthlyRevenueByZone",
    "booking_status_monthly": "rpt.usp_BookingStatusMonthly",
    "cleaner_monthly": "rpt.usp_CleanerMonthly",
    "new_customers_monthly": "rpt.usp_NewCustomersMonthly",
}

SQL_DIR = Path(__file__).resolve().parents[2] / "legacy" / "sqlserver"


def connect(host: str, port: int, user: str, password: str, database: str = "master"):
    import pymssql

    return pymssql.connect(server=host, port=port, user=user, password=password, database=database, autocommit=True)


def run_script(conn, path: Path) -> None:
    batches = re.split(r"^\s*GO\s*$", path.read_text(), flags=re.MULTILINE | re.IGNORECASE)
    cur = conn.cursor()
    for batch in batches:
        if batch.strip():
            cur.execute(batch)


def _literal(v) -> str:
    if v is None or v is pd.NaT:
        return "NULL"
    if isinstance(v, float) and math.isnan(v):
        return "NULL"
    if isinstance(v, (bool,)) or type(v).__name__ == "bool_":
        return "1" if v else "0"
    if isinstance(v, pd.Timestamp):
        return f"'{v.strftime('%Y-%m-%d %H:%M:%S')}'"
    if isinstance(v, (dt.datetime,)):
        return f"'{v.strftime('%Y-%m-%d %H:%M:%S')}'"
    if isinstance(v, dt.date):
        return f"'{v.isoformat()}'"
    if isinstance(v, str):
        return "N'" + v.replace("'", "''") + "'"
    if isinstance(v, float):
        return repr(round(v, 4))
    return str(v)


def load_current_state(conn, current: dict[str, pd.DataFrame], batch_rows: int = 900) -> dict[str, int]:
    cur = conn.cursor()
    counts = {}
    for table in LOAD_ORDER:
        cols = COLUMNS[table]
        df = current[table][cols].astype(object).where(current[table][cols].notna(), None)
        rows = df.itertuples(index=False, name=None)
        buf: list[str] = []
        n = 0
        for row in rows:
            buf.append("(" + ",".join(_literal(v) for v in row) + ")")
            if len(buf) == batch_rows:
                cur.execute(f"INSERT INTO ops.{table} ({','.join(cols)}) VALUES " + ",".join(buf))
                n += len(buf)
                buf = []
        if buf:
            cur.execute(f"INSERT INTO ops.{table} ({','.join(cols)}) VALUES " + ",".join(buf))
            n += len(buf)
        counts[table] = n
    return counts


def build_database(conn, current: dict[str, pd.DataFrame]) -> dict[str, int]:
    run_script(conn, SQL_DIR / "01_schema.sql")
    conn.cursor().execute("USE ucleany_ops")
    counts = load_current_state(conn, current)
    run_script(conn, SQL_DIR / "02_reports.sql")
    return counts


def export_reports(conn, out_dir: str | Path, from_month: str, to_month: str) -> dict[str, int]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cur = conn.cursor()
    cur.execute("USE ucleany_ops")
    exported = {}
    for name, proc in REPORTS.items():
        cur.execute(f"EXEC {proc} @FromMonth = %s, @ToMonth = %s", (from_month, to_month))
        cols = [c[0] for c in cur.description]
        rows = cur.fetchall()
        with open(out_dir / f"{name}.csv", "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(cols)
            for r in rows:
                w.writerow([_csv_value(v) for v in r])
        exported[name] = len(rows)
    return exported


def _csv_value(v):
    if v is None:
        return ""
    if isinstance(v, Decimal):
        return format(v, "f")
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()[:10]
    return v


def write_manifest(out_dir, cfg, from_month: str, to_month: str, loaded: dict, exported: dict, data_fingerprint: str) -> None:
    manifest = {
        "description": "Outputs of the legacy rpt.* procedures on SQL Server, used as the reconciliation baseline.",
        "from_month": from_month,
        "to_month": to_month,
        "generator": dataclasses.asdict(cfg),
        "data_fingerprint": data_fingerprint,
        "rows_loaded": loaded,
        "rows_exported": exported,
    }
    Path(out_dir, "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
