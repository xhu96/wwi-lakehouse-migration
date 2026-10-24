import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("PYSPARK_PYTHON", sys.executable)

from ucleany.synth.generate import ScenarioConfig, generate  # noqa: E402

SNAPSHOTS = ROOT / "legacy" / "report_snapshots"


@pytest.fixture(scope="session")
def dataset():
    return generate(ScenarioConfig())


@pytest.fixture(scope="session")
def spark(tmp_path_factory):
    from ucleany.local_runner import spark_session

    session = spark_session(str(tmp_path_factory.mktemp("warehouse")))
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()
