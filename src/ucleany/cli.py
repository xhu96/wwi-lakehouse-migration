"""Command line entry point.

ucleany generate --out data/landing            # write the CDC landing zone
ucleany legacy --password ... --snapshots legacy/report_snapshots
ucleany local-run --landing data/landing --snapshots legacy/report_snapshots
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .synth.generate import ScenarioConfig, fingerprint, generate


def _config(args) -> ScenarioConfig:
    return ScenarioConfig(scale=args.scale, seed=args.seed, end=args.end)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ucleany")
    p.add_argument("--scale", type=float, default=1.0, help="volume multiplier (CI uses 0.05)")
    p.add_argument("--seed", type=int, default=ScenarioConfig.seed)
    p.add_argument("--end", default=ScenarioConfig.end, help="extract date, YYYY-MM-DD")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="write the landing zone as parquet")
    g.add_argument("--out", required=True)

    lg = sub.add_parser("legacy", help="build the legacy SQL Server database and export its reports")
    lg.add_argument("--host", default=os.environ.get("MSSQL_HOST", "localhost"))
    lg.add_argument("--port", type=int, default=int(os.environ.get("MSSQL_PORT", "1433")))
    lg.add_argument("--user", default=os.environ.get("MSSQL_USER", "sa"))
    lg.add_argument("--password", default=os.environ.get("MSSQL_SA_PASSWORD"))
    lg.add_argument("--snapshots", required=True)

    lr = sub.add_parser("local-run", help="run bronze/silver/gold and the reconciliation on local Spark")
    lr.add_argument("--landing", required=True)
    lr.add_argument("--snapshots", required=True)
    lr.add_argument("--warehouse", default="data/spark-warehouse")
    lr.add_argument("--report", default=None, help="write the reconciliation report as markdown")

    args = p.parse_args(argv)
    cfg = _config(args)

    if args.cmd == "generate":
        from .synth.landing import write_landing

        ds = generate(cfg)
        print(json.dumps(write_landing(ds, args.out), indent=2))
        return 0

    if args.cmd == "legacy":
        from . import legacy

        if not args.password:
            p.error("--password or MSSQL_SA_PASSWORD is required")
        ds = generate(cfg)
        conn = legacy.connect(args.host, args.port, args.user, args.password)
        loaded = legacy.build_database(conn, ds.current)
        print(json.dumps(loaded, indent=2))
        from_month = cfg.start_ts.strftime("%Y-%m-01")
        to_month = cfg.as_of_ts.strftime("%Y-%m-01")
        exported = legacy.export_reports(conn, args.snapshots, from_month, to_month)
        legacy.write_manifest(args.snapshots, cfg, from_month, to_month, loaded, exported, fingerprint(ds))
        print(json.dumps(exported, indent=2))
        return 0

    if args.cmd == "local-run":
        from .local_runner import run

        ok = run(args.landing, args.snapshots, args.warehouse, report_path=args.report)
        return 0 if ok else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
