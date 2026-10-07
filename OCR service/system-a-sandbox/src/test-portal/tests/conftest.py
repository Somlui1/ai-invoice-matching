"""Test harness.

The portal has no engine of its own, so the tests need System A as a library - but not the Standard of whoever
happens to run them.  The harness therefore copies the ``system_a`` package found under ``SYSTEM_A_HOME`` next to
a *stub* Standard (``tests/system_a_stub/config``) into a temp folder and imports it from there, and it also
copies the repository's entrypoint ``process_pdf.py`` so ``webapp.sysa`` can be imported for real.

The payload every test asserts on is produced by System A itself: ``synth.payload()`` feeds a synthetic
``aiva.extraction/2.0`` to ``orchestrator.validate()`` with ``build_services()`` in sandbox mode (in-memory
Oracle + sim AI).  No VLM, no Oracle and no Paperless is contacted here.
"""
import os
import shutil
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for p in (str(ROOT), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("SYSTEM_A_MODE", "sandbox")
os.environ.setdefault("SYSTEM_A_AI_MODE", "sim")


def _find_package() -> Path:
    from webapp.config import load_dotenv
    load_dotenv(ROOT / ".env")
    home = os.environ.get("SYSTEM_A_HOME")
    candidates = []
    if home:
        candidates.extend([Path(home) / "src" / "system_a", Path(home) / "system_a", Path(home)])
    try:
        candidates.extend([ROOT.parents[1] / "src" / "system_a", ROOT.parents[1] / "system_a"])
    except Exception:
        pass
    for cand in candidates:
        if (cand / "__init__.py").is_file() and (cand / "domain").is_dir():
            return cand
    pytest.exit("set SYSTEM_A_HOME to the System A project folder (the one that has src/system_a)", returncode=2)


@pytest.fixture(scope="session")
def harness(tmp_path_factory) -> Path:
    """A System A project root of our own: the real package, the stub Standard, the real entrypoint."""
    return make_harness(tmp_path_factory.mktemp("system_a_home"))


def _copy(src: Path, dst: Path) -> None:
    """Copy a file or folder over ``dst``, replacing whatever is there (a rerun must not mix versions)."""
    if dst.is_dir():
        shutil.rmtree(dst)
    elif dst.exists():
        dst.unlink()
    if src.is_dir():
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def make_harness(dest) -> Path:
    """Copy the real ``system_a`` over a stub Standard into *dest* and import it from there.

    Module level so a plain script (``python tests/probe.py``) can build the same harness the tests use.
    """
    real_root = _find_package().parents[1]
    h = Path(dest)
    _copy(_find_package(), h / "src" / "system_a")
    _copy(HERE / "system_a_stub" / "config", h / "config")
    for f in ("process_pdf.py", "schemas"):                            # sysa.init() imports process_pdf
        if (real_root / f).exists():
            _copy(real_root / f, h / f)
    if str(h / "src") not in sys.path:
        sys.path.insert(0, str(h / "src"))
    return h


def standard_buyer() -> dict:
    """The buyer of the stub Standard - what the portal passes to System A on every call."""
    from system_a.domain.standard import load_standard
    e = load_standard().entities[103]
    return {"tax_id": e["tax_id"], "name_th": e["name_th"], "addr_th": e["addr_th"]}


@pytest.fixture(scope="session")
def buyer(harness):
    return standard_buyer()


def _payload(buyer, *, inv="SYN-INV-0001", po="50000001", lines=None, dataset="auto", **kw) -> dict:
    import synth
    lines = list(lines or [synth.BRACKET, synth.GASKET])
    if dataset == "auto":
        dataset = synth.oracle_dataset(inv=inv, po=po, lines=lines)
    elif dataset is None:
        dataset = synth.oracle_dataset(inv=inv, po=po, lines=lines, with_receipt=False)
    return synth.payload(buyer=buyer, ext=synth.extraction(buyer=buyer, inv=inv, po=po, lines=lines, **kw),
                         dataset=dataset)


@pytest.fixture(scope="session")
def payload(harness, buyer) -> dict:
    """A clean synthetic invoice: System A's own result 3.0, recommendation AUTO_PASS."""
    return _payload(buyer)


@pytest.fixture(scope="session")
def hold_payload(harness, buyer) -> dict:
    """Same invoice, but Oracle has no receipt for it: the rules say so, with evidence pointing at elements."""
    return _payload(buyer, inv="SYN-INV-0009", po="50000009", dataset=None)


@pytest.fixture(scope="session")
def elements(payload) -> dict:
    return {e["element_id"]: e for e in payload["ocr"]["elements"]}


# --------------------------------------------------------------------------- the portal, wired to doubles
@pytest.fixture
def settings(harness, tmp_path):
    from webapp.config import Settings
    return Settings(system_a_home=harness, data_dir=tmp_path / "data", workers=2, render_dpi=96,
                    paperless_tag="invoice", paperless_limit=50, mode="sandbox", persist_results=True)


@pytest.fixture
def sa(payload):
    from doubles import FakeSystemA
    return FakeSystemA(payload)


@pytest.fixture
def catalog(sa, settings):
    """The real :class:`webapp.catalog.Catalog`, reading through a stand-in Paperless client."""
    from webapp.catalog import Catalog
    c = Catalog(sa, tag=settings.paperless_tag, limit=settings.paperless_limit)
    c.refresh()
    return c


@pytest.fixture
def parts(settings, sa, catalog):
    """``(app, service, catalog)`` with the real service + store and a runner that returns the real payload."""
    from doubles import FakeRunner
    from webapp.app import create_app
    from webapp.service import DocumentService
    from webapp.store import ResultStore

    service = DocumentService(catalog, FakeRunner(payload=sa.payload), ResultStore(settings.data_dir),
                              workers=2, mode="sandbox")
    yield create_app(settings, service, catalog), service, catalog
    service.shutdown()


@pytest.fixture
def client(parts):
    from fastapi.testclient import TestClient
    return TestClient(parts[0])
