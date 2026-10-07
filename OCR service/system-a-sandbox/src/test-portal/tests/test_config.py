"""The portal's own configuration: almost none of it, and the one hard requirement - where System A lives."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

import webapp.config as cfg
from webapp.config import Settings, SystemAUnavailable, ensure_system_a, load_dotenv

PORTAL_VARS = ("WEBAPP_HOST", "WEBAPP_PORT", "WEBAPP_DATA_DIR", "WEBAPP_WORKERS", "WEBAPP_RENDER_DPI",
               "WEBAPP_PERSIST", "WEBAPP_QUICK", "SYSTEM_A_HOME", "SYSTEM_A_ENGINE", "SYSTEM_A_URL",
               "SYSTEM_A_API_KEY", "SYSTEM_A_HTTP_TIMEOUT", "SYSTEM_A_MODE", "PAPERLESS_TAG", "PAPERLESS_LIMIT")


@pytest.fixture
def clean_env(monkeypatch):
    """A process as if nothing were configured, so the defaults and the file are really what is read."""
    for k in PORTAL_VARS:
        monkeypatch.delenv(k, raising=False)


def test_dotenv_fills_the_environment_but_never_overrides_it(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text('\ufeff# comment\r\nA=1\r\n B = two \r\nC="three"\r\nD=4 # trailing\r\n\r\nbad line\r\nE=\r\n',
                 encoding="utf-8")
    monkeypatch.setenv("A", "from-the-real-environment")
    got = load_dotenv(f)
    assert got == {"A": "1", "B": "two", "C": "three", "D": "4", "E": ""}    # what the file says
    assert os.environ["A"] == "from-the-real-environment"                    # what the process actually uses
    assert os.environ["B"] == "two" and os.environ["D"] == "4"
    assert "bad line" not in os.environ
    monkeypatch.undo()


def test_a_missing_dotenv_is_not_an_error(tmp_path):
    assert load_dotenv(tmp_path / "nope.env") == {}


def test_the_defaults_are_a_local_read_only_portal(clean_env):
    s = Settings.from_env(env_file=Path(__file__).parents[1] / "nothing.env")
    assert (s.host, s.port) == ("127.0.0.1", 8090)               # never bound to the network by default
    assert s.engine == "inprocess" and s.mode == "production" and s.system_a_key == ""
    assert s.workers == 4 and s.render_dpi == 150 and s.persist_results is True and s.quick is False
    assert s.paperless_tag == "invoice" and s.paperless_limit == 200
    assert s.data_dir == Path(__file__).resolve().parents[1] / "data"


def test_the_environment_is_the_whole_configuration(clean_env, monkeypatch, tmp_path):
    for k, v in {"WEBAPP_HOST": "0.0.0.0", "WEBAPP_PORT": "9000", "WEBAPP_DATA_DIR": str(tmp_path),
                 "WEBAPP_WORKERS": "8", "WEBAPP_RENDER_DPI": "96", "WEBAPP_PERSIST": "false",
                 "WEBAPP_QUICK": "1", "SYSTEM_A_HOME": str(tmp_path / "sa"), "SYSTEM_A_ENGINE": "HTTP",
                 "SYSTEM_A_URL": "https://sys-a.internal/", "SYSTEM_A_API_KEY": "k", "SYSTEM_A_HTTP_TIMEOUT": "60",
                 "SYSTEM_A_MODE": "Sandbox", "PAPERLESS_TAG": "  tax-invoice  ", "PAPERLESS_LIMIT": "25"}.items():
        monkeypatch.setenv(k, v)
    s = Settings.from_env(env_file=tmp_path / "absent.env")
    assert (s.host, s.port, s.workers, s.render_dpi) == ("0.0.0.0", 9000, 8, 96)
    assert s.data_dir == tmp_path and s.persist_results is False and s.quick is True
    assert s.system_a_home == tmp_path / "sa" and s.engine == "http"      # case-insensitive on purpose
    assert s.system_a_url == "https://sys-a.internal" and s.system_a_key == "k" and s.http_timeout_s == 60.0
    assert s.mode == "sandbox" and s.paperless_tag == "tax-invoice" and s.paperless_limit == 25


def test_a_dotenv_file_configures_it_too(clean_env, tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("WEBAPP_PORT=8123\nSYSTEM_A_ENGINE=http\nPAPERLESS_TAG=scan\nWEBAPP_RENDER_DPI=72\n",
                 encoding="utf-8")
    s = Settings.from_env(env_file=f)
    assert (s.port, s.engine, s.paperless_tag, s.render_dpi) == (8123, "http", "scan", 72)
    monkeypatch.undo()


@pytest.mark.parametrize("var,val,why", [
    ("SYSTEM_A_ENGINE", "grpc", "SYSTEM_A_ENGINE"),
    ("SYSTEM_A_MODE", "dev", "SYSTEM_A_MODE"),
    ("WEBAPP_WORKERS", "0", "WEBAPP_WORKERS"),
    ("WEBAPP_RENDER_DPI", "30", "72-400"),
    ("PAPERLESS_LIMIT", "0", "PAPERLESS_LIMIT"),
    ("PAPERLESS_TAG", " ", "PAPERLESS_TAG"),
])
def test_a_setting_that_cannot_work_is_refused_before_the_server_starts(clean_env, monkeypatch, var, val, why):
    monkeypatch.setenv(var, val)
    with pytest.raises(ValueError, match=why):
        Settings.from_env(env_file=Path(__file__).parents[1] / "nothing.env")


# ------------------------------------------------------------------ finding System A
def test_an_already_importable_system_a_is_the_one_used(harness):
    assert ensure_system_a(None) == harness                      # imported by another test: no guesswork
    assert str(harness) in sys.path                              # so process_pdf.py next to it is importable too


@pytest.fixture
def no_system_a_importable(monkeypatch, tmp_path):
    """Pretend nothing has imported System A and that the portal lives where no System A is installed."""
    monkeypatch.setitem(sys.modules, "system_a", None)           # import system_a -> ImportError
    monkeypatch.setattr(cfg, "ROOT", tmp_path / "portal")
    (tmp_path / "portal").mkdir()
    return tmp_path


def test_a_home_without_a_system_a_is_named_in_the_error(no_system_a_importable, tmp_path):
    with pytest.raises(SystemAUnavailable, match="no system_a package under"):
        cfg.ensure_system_a(tmp_path / "not-system-a")


def test_no_home_at_all_says_what_to_set(no_system_a_importable):
    with pytest.raises(SystemAUnavailable, match="SYSTEM_A_HOME is not set"):
        cfg.ensure_system_a(None)


# ------------------------------------------------------------------ a cold process, the way run.bat starts it
def test_a_fresh_process_finds_system_a_from_its_home(harness):
    out = run_portal_python(f"from pathlib import Path; from webapp.config import ensure_system_a;"
                            f"print(ensure_system_a(Path(r'{harness}')))")
    assert Path(out) == harness


def test_a_fresh_process_without_a_home_uses_the_project_it_lives_in():
    out = run_portal_python("from webapp.config import ensure_system_a; print(ensure_system_a(None))")
    assert (Path(out) / "src" / "system_a").is_dir()             # found by the folder layout, not by a guess
    assert Path(out) == Path(os.environ["SYSTEM_A_HOME"]).resolve() or Path(out).name


def run_portal_python(code: str) -> str:
    """Run a snippet with the portal on sys.path and System A unconfigured - a real interpreter, no fixtures."""
    root = Path(__file__).resolve().parents[1]
    env = {k: v for k, v in os.environ.items() if k not in ("SYSTEM_A_HOME", "PYTHONPATH")}
    p = subprocess.run([sys.executable, "-c", code], cwd=str(root), capture_output=True, text=True, env=env)
    assert p.returncode == 0, p.stdout + p.stderr
    return p.stdout.strip()
