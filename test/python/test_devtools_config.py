"""Tests for bin/devtools-config.py, imported by path because its name is not a module name."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "bin" / "devtools-config.py"
spec = importlib.util.spec_from_file_location("devtools_config", SCRIPT)
assert spec and spec.loader
devtools_config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(devtools_config)


@pytest.fixture
def config(tmp_path, monkeypatch):
    """Change into a scratch repository and return a writer for its devtools.toml."""
    monkeypatch.chdir(tmp_path)

    def write(text: str) -> Path:
        path = tmp_path / "devtools.toml"
        path.write_text(text)
        return path

    return write


def run(capsys, *argv: str) -> tuple[int, str, str]:
    """Run main() and return its status, stdout and stderr."""
    status = devtools_config.main(list(argv))
    out, err = capsys.readouterr()
    return status, out, err


def test_prints_a_string(config, capsys):
    config('[fetch]\nref = "v1"\n')
    assert run(capsys, "fetch.ref") == (0, "v1\n", "")


def test_prints_numbers_and_booleans(config, capsys):
    config("[t]\nport = 8000\nratio = 0.5\non = true\noff = false\n")
    assert run(capsys, "t.port")[1] == "8000\n"
    assert run(capsys, "t.ratio")[1] == "0.5\n"
    assert run(capsys, "t.on")[1] == "true\n"
    assert run(capsys, "t.off")[1] == "false\n"


def test_prints_a_list_one_item_per_line(config, capsys):
    config('[dev]\ncompose_files = ["a.yml", "b.yml"]\n')
    assert run(capsys, "dev.compose_files") == (0, "a.yml\nb.yml\n", "")


def test_prints_a_list_of_lists_tab_separated(config, capsys):
    config('[compose]\nstacks = [["a.yml"], ["a.yml", "my b.yml"]]\n')
    assert run(capsys, "compose.stacks") == (0, "a.yml\na.yml\tmy b.yml\n", "")


def test_prints_nothing_for_an_empty_list(config, capsys):
    config("[compose]\nstacks = []\n")
    assert run(capsys, "compose.stacks") == (0, "", "")


def test_reads_another_file_with_config(tmp_path, capsys):
    other = tmp_path / "other.toml"
    other.write_text('[fetch]\nref = "main"\n')
    assert run(capsys, "--config", str(other), "fetch.ref") == (0, "main\n", "")


def test_missing_key_names_the_table_and_key(config, capsys):
    config("[compose]\n")
    status, out, err = run(capsys, "compose.stacks")
    assert (status, out) == (1, "")
    assert err == (
        "devtools-config: devtools.toml sets no compose.stacks; add stacks to its [compose] table\n"
    )


def test_missing_table_is_a_missing_key(config, capsys):
    config('[fetch]\nref = "v1"\n')
    status, _, err = run(capsys, "dev.compose_files")
    assert status == 1
    assert "sets no dev.compose_files" in err


def test_default_lines_stand_in_for_a_missing_key(config, capsys):
    config("[fetch]\n")
    status, out, _ = run(capsys, "--default", "a.yml", "--default", "b.yml", "dev.compose_files")
    assert (status, out) == (0, "a.yml\nb.yml\n")


def test_a_default_does_not_override_a_set_key(config, capsys):
    config('[dev]\ncompose_files = ["set.yml"]\n')
    assert run(capsys, "--default", "a.yml", "dev.compose_files")[1] == "set.yml\n"


@pytest.mark.parametrize("key", ["fetch", "fetch.", ".ref", "a.b.c"])
def test_rejects_a_key_that_is_not_table_dot_key(config, capsys, key):
    config("[fetch]\n")
    status, _, err = run(capsys, key)
    assert status == 1
    assert err == f"devtools-config: {key!r} is not TABLE.KEY\n"


def test_missing_file_says_where_to_run(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    status, _, err = run(capsys, "fetch.ref")
    assert status == 1
    assert err == "devtools-config: no devtools.toml; run this from the repository root\n"


def test_invalid_toml(config, capsys):
    config("[fetch\n")
    status, _, err = run(capsys, "fetch.ref")
    assert status == 1
    assert err.startswith("devtools-config: devtools.toml is not valid TOML: ")


def test_a_table_name_that_holds_a_value(config, capsys):
    config('fetch = "v1"\n')
    status, _, err = run(capsys, "fetch.ref")
    assert status == 1
    assert err == "devtools-config: fetch in devtools.toml must be a table\n"


@pytest.mark.parametrize(
    "value",
    ['"two\\nlines"', '"a\\tb"', '["ok", "bad\\n"]', '[["a", "b\\tc"]]'],
)
def test_rejects_values_a_line_cannot_carry(config, capsys, value):
    config(f"[t]\nk = {value}\n")
    status, out, err = run(capsys, "t.k")
    assert (status, out) == (1, "")
    assert err == "devtools-config: t.k holds a newline or tab, which a shell cannot read back\n"


@pytest.mark.parametrize("value", ["{ a = 1 }", "[{ a = 1 }]", "[[[1]]]", "1979-05-27"])
def test_rejects_tables_deep_nesting_and_dates(config, capsys, value):
    config(f"[t]\nk = {value}\n")
    status, _, err = run(capsys, "t.k")
    assert status == 1
    assert err == (
        "devtools-config: t.k must hold strings, numbers or booleans, or lists of them\n"
    )


@pytest.mark.parametrize("value", ['["a", "b"]', "[]"])
def test_shape_list_accepts_a_list_of_scalars(config, capsys, value):
    config(f"[t]\nk = {value}\n")
    assert run(capsys, "--shape", "list", "t.k")[0] == 0


@pytest.mark.parametrize("value", ['"a"', '[["a"]]', '["a", ["b"]]'])
def test_shape_list_rejects_anything_else(config, capsys, value):
    config(f"[t]\nk = {value}\n")
    status, out, err = run(capsys, "--shape", "list", "t.k")
    assert (status, out) == (1, "")
    assert err == 'devtools-config: t.k must be a list, such as ["a", "b"]\n'


@pytest.mark.parametrize("value", ['[["a"], ["a", "b"]]', "[]"])
def test_shape_lists_accepts_a_list_of_non_empty_lists(config, capsys, value):
    config(f"[t]\nk = {value}\n")
    assert run(capsys, "--shape", "lists", "t.k")[0] == 0


@pytest.mark.parametrize("value", ['"a"', '["a", "b"]', '[["a"], []]', '[["a"], "b"]'])
def test_shape_lists_rejects_anything_else(config, capsys, value):
    config(f"[t]\nk = {value}\n")
    status, out, err = run(capsys, "--shape", "lists", "t.k")
    assert (status, out) == (1, "")
    assert "t.k must be a list of non-empty lists" in err


def test_shape_does_not_apply_to_defaults(config, capsys):
    config("[t]\n")
    assert run(capsys, "--shape", "lists", "--default", "a", "t.k")[1] == "a\n"


def test_runs_as_a_script(config):
    config('[fetch]\nref = "v1"\n')
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "fetch.ref"], capture_output=True, text=True, check=False
    )
    assert (result.returncode, result.stdout) == (0, "v1\n")
