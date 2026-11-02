"""config/ruff.toml, extended from .devtools/config/ the way a repository uses it."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[2] / "config" / "ruff.toml"

# An unused argument, which the base reports outside tests.
UNUSED_ARGUMENT = "def handler(request):\n    return 1\n"
# What `alembic revision --autogenerate` writes: an over-long line, and `alembic` before
# `sqlalchemy`, which is out of order when ruff takes the local alembic/ for a package.
MIGRATION = (
    '"""' + "x" * 120 + '"""\n\nfrom alembic import op\nimport sqlalchemy as sa\n\n'
    "def upgrade():\n    op.add_column('t', sa.Column('c', sa.Integer()))\n"
)


@pytest.fixture
def repo(tmp_path):
    """A scratch repository whose ruff.toml extends the fetched base."""
    (tmp_path / ".devtools" / "config").mkdir(parents=True)
    shutil.copy(BASE, tmp_path / ".devtools" / "config" / "ruff.toml")
    (tmp_path / "ruff.toml").write_text('extend = ".devtools/config/ruff.toml"\n')
    return tmp_path


def ruff(repo: Path) -> str:
    """Run ruff over the repository and return its findings, one `path:CODE` per line."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "-q",
            "--no-cache",
            "--output-format",
            "concise",
            ".",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout


def write(path: Path, text: str) -> None:
    """Write a file, creating its directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_reports_an_unused_argument_outside_tests(repo):
    write(repo / "app" / "views.py", UNUSED_ARGUMENT)
    assert "app/views.py:1:13: ARG001" in ruff(repo)


@pytest.mark.parametrize("directory", ["tests", "test", "backend/tests", "backend/test"])
def test_ignores_unused_arguments_in_tests(repo, directory):
    write(repo / directory / "test_views.py", UNUSED_ARGUMENT)
    assert ruff(repo) == ""


@pytest.mark.parametrize("root", [".", "backend"])
def test_ignores_what_alembic_generates(repo, root):
    write(repo / root / "alembic" / "__init__.py", "")
    write(repo / root / "alembic" / "versions" / "0001_add_c.py", MIGRATION)
    assert ruff(repo) == ""


def test_checks_the_rest_of_alembic(repo):
    write(repo / "alembic" / "env.py", "x = '" + "y" * 120 + "'\n")
    assert "alembic/env.py:1:101: E501" in ruff(repo)
