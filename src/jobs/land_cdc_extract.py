"""Write the CDC extract to the landing volume.

In production this step is the SQL Server change data capture export. Here the
synthetic generator produces the same change files, with the exact parameters
recorded in the legacy snapshot manifest, so the lakehouse can be reconciled
with the reports the legacy database produced.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--catalog", required=True)
p.add_argument("--src", required=True, help="folder that contains the ucleany package")
p.add_argument("--snapshots", required=True, help="legacy report snapshot folder (manifest.json)")
p.add_argument("--reset", default="true", help="delete existing landing files first")
args = p.parse_args()

sys.path.append(args.src)

from ucleany.synth.generate import ScenarioConfig, fingerprint, generate  # noqa: E402
from ucleany.synth.landing import write_landing  # noqa: E402

manifest = json.loads((Path(args.snapshots) / "manifest.json").read_text())
cfg = ScenarioConfig(**manifest["generator"])
ds = generate(cfg)

fp = fingerprint(ds)
if fp != manifest["data_fingerprint"]:
    raise RuntimeError(
        f"Generated data fingerprint {fp} differs from the legacy baseline {manifest['data_fingerprint']}. "
        "Check the pinned numpy/pandas versions in the job environment."
    )

landing = Path(f"/Volumes/{args.catalog}/landing/cdc")
if args.reset.lower() == "true" and landing.exists():
    for child in landing.iterdir():
        shutil.rmtree(child) if child.is_dir() else child.unlink()
print(json.dumps(write_landing(ds, landing), indent=2))
