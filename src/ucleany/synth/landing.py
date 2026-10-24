"""Write the change feed to a landing zone the way the SQL Server extract does.

Layout: ``<root>/<table>/batch=YYYY-MM/part-00000.parquet``, one batch per
month of commits. Timestamps recorded in UTC are written as UTC instants;
``bookings.scheduled_start`` is Rome wall-clock time and stays naive, exactly
as it is stored in the operational database.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .generate import SyntheticDataset

# Columns that hold local (Europe/Rome) wall-clock time in the source system.
LOCAL_TIME_COLUMNS = {("bookings", "scheduled_start")}
DATE_COLUMNS = {("marketing_spend", "month_start")}


def to_landing_frame(table: str, df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if (table, col) in DATE_COLUMNS:
            out[col] = pd.to_datetime(out[col]).dt.date
        elif pd.api.types.is_datetime64_any_dtype(out[col]) and (table, col) not in LOCAL_TIME_COLUMNS:
            out[col] = pd.to_datetime(out[col]).astype("datetime64[us]").dt.tz_localize("UTC")
        elif pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].astype("datetime64[us]")
    return out


def write_landing(ds: SyntheticDataset, root: str | Path) -> dict[str, int]:
    root = Path(root)
    written: dict[str, int] = {}
    for table, df in ds.changes.items():
        frame = to_landing_frame(table, df)
        schema = pa.Schema.from_pandas(frame, preserve_index=False)
        batches = pd.to_datetime(df["_commit_ts"]).dt.strftime("%Y-%m")
        for batch, part in frame.groupby(batches.to_numpy(), sort=True):
            target = root / table / f"batch={batch}"
            target.mkdir(parents=True, exist_ok=True)
            pq.write_table(pa.Table.from_pandas(part, schema=schema, preserve_index=False), target / "part-00000.parquet")
        written[table] = len(frame)
    return written
