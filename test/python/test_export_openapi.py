"""Tests for bin/export-openapi.py, with a stand-in app module on the import path."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "bin" / "export-openapi.py"
spec = importlib.util.spec_from_file_location("export_openapi", SCRIPT)
assert spec and spec.loader
export_openapi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export_openapi)

APP_MODULE = """
from pathlib import Path

seen = []

class App:
    def __init__(self, data_dir):
        self.data_dir = data_dir

    def openapi(self):
        seen.append((self.data_dir, self.data_dir.is_dir()))
        return {"paths": {"/b": {}, "/a": {}}, "info": {"title": "T", "version": "1.2.3"}}

def build(data_dir: Path):
    return App(data_dir)

no_version = lambda data_dir: type("A", (), {"openapi": lambda self: {"paths": {}}})()
not_callable = 42
"""


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A scratch repository with a stand-in app module importable as fakeapp."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "fakeapp.py").write_text(APP_MODULE)
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("fakeapp", None)
    return tmp_path


def run(capsys, app: str | None) -> tuple[int, str, str]:
    """Write devtools.toml naming the app, run main() and return status, stdout and stderr."""
    Path("devtools.toml").write_text(f'[openapi]\napp = "{app}"\n' if app else "[openapi]\n")
    status = export_openapi.main([])
    out, err = capsys.readouterr()
    return status, out, err


def test_prints_the_schema_sorted_with_the_version_fixed(repo, capsys):
    status, out, err = run(capsys, "fakeapp:build")
    assert (status, err) == (0, "")
    assert (
        out
        == json.dumps(
            {"info": {"title": "T", "version": "0.0.0"}, "paths": {"/a": {}, "/b": {}}},
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def test_builds_the_app_in_a_scratch_directory_that_is_removed(repo, capsys):
    run(capsys, "fakeapp:build")
    import fakeapp

    [(data_dir, existed)] = fakeapp.seen
    assert existed
    assert not data_dir.exists()
    assert repo not in data_dir.parents


def test_adds_a_version_to_a_schema_without_info(repo, capsys):
    status, out, _ = run(capsys, "fakeapp:no_version")
    assert status == 0
    assert json.loads(out)["info"] == {"version": "0.0.0"}


@pytest.mark.parametrize("reference", ["fakeapp", "fakeapp:", ":build"])
def test_rejects_a_reference_that_is_not_module_colon_callable(repo, capsys, reference):
    status, out, err = run(capsys, reference)
    assert (status, out) == (1, "")
    assert err == f"export-openapi: openapi.app must be module:callable, not {reference!r}\n"


def test_reports_a_module_that_cannot_be_imported(repo, capsys):
    status, _, err = run(capsys, "no_such_module:build")
    assert status == 1
    assert err.startswith("export-openapi: cannot import no_such_module: ")


@pytest.mark.parametrize("attribute", ["missing", "not_callable"])
def test_reports_an_attribute_that_is_not_callable(repo, capsys, attribute):
    status, _, err = run(capsys, f"fakeapp:{attribute}")
    assert status == 1
    assert err == f"export-openapi: fakeapp has no callable {attribute}\n"


def test_names_the_setting_when_devtools_toml_lacks_it(repo, capsys):
    status, _, err = run(capsys, None)
    assert status == 1
    assert err == (
        "export-openapi: devtools.toml sets no openapi.app; add app to its [openapi] table\n"
    )


def test_runs_as_a_script(repo):
    Path("devtools.toml").write_text('[openapi]\napp = "fakeapp:build"\n')
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": str(repo), "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["info"]["version"] == "0.0.0"
