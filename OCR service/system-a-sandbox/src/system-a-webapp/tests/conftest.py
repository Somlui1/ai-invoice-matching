"""Test harness.

The tests need System A as a library but must not depend on the Standard of whoever runs them, so the harness
copies the ``system_a`` package found under ``SYSTEM_A_HOME`` next to a *stub* Standard (``tests/system_a_stub/config``)
in a temp folder and imports it from there.  The synthetic batch is addressed to the buyer of that Standard.
"""
import os
import shutil
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for p in (ROOT,):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

os.environ.setdefault("SYSTEM_A_MODE", "sandbox")
os.environ.setdefault("SYSTEM_A_AI_MODE", "sim")
os.environ["PERCEPTION_TABLE"] = "0"          # the live-perception test drives the page-items pass only
os.environ["PERCEPTION_CROPS"] = "0"
os.environ["PERCEPTION_CLASSIFY"] = "0"


def _find_package() -> Path:
    home = os.environ.get("SYSTEM_A_HOME")
    if not home:
        pytest.exit("set SYSTEM_A_HOME to the System A project folder (the one that has src/system_a)", returncode=2)
    for cand in (Path(home) / "src" / "system_a", Path(home) / "system_a", Path(home)):
        if (cand / "__init__.py").is_file() and (cand / "domain").is_dir():
            return cand
    pytest.exit(f"no system_a package under SYSTEM_A_HOME={home}", returncode=2)


@pytest.fixture(scope="session")
def harness(tmp_path_factory) -> Path:
    h = tmp_path_factory.mktemp("system_a_home")
    shutil.copytree(_find_package(), h / "src" / "system_a", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(HERE / "system_a_stub" / "config", h / "config")
    sys.path.insert(0, str(h / "src"))
    return h


@pytest.fixture(scope="session")
def buyer(harness):
    from system_a.domain.standard import load_standard
    e = load_standard().entities[103]
    return {"tax_id": e["tax_id"], "name_th": e["name_th"], "addr_th": e["addr_th"]}


@pytest.fixture(scope="session")
def batch_dir(harness, buyer, tmp_path_factory) -> Path:
    from webapp.demo import write_batch
    out = tmp_path_factory.mktemp("batch")
    write_batch(out, buyer)
    return out


@pytest.fixture(scope="session")
def oracle_dataset(batch_dir) -> dict:
    import json
    return json.loads((batch_dir / "oracle_dataset.json").read_text(encoding="utf-8"))


@pytest.fixture
def settings(harness, batch_dir, tmp_path):
    from webapp.config import Settings
    return Settings(batch_path=batch_dir, data_dir=tmp_path / "data", system_a_home=harness, workers=4)


@pytest.fixture
def parts(settings, oracle_dataset):
    """(app, service, batch) with the real in-process engine and replay perception."""
    from webapp.build import build_all
    from webapp.engine import InProcessEngine
    app, service, batch = build_all(settings, engine=InProcessEngine(oracle_dataset))
    yield app, service, batch
    service.shutdown()


@pytest.fixture
def client(parts):
    from fastapi.testclient import TestClient
    return TestClient(parts[0])
