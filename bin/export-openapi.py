#!/usr/bin/env python3
"""Print an application's OpenAPI schema, in a form that diffs cleanly when committed.

The app is built by a callable the repository names in devtools.toml, which is given a scratch
data directory and returns an object with an ``openapi()`` method, such as a FastAPI app:

    [openapi]
    app = "myapp.api.schema:build_app"

    def build_app(data_dir: Path) -> FastAPI:
        return create_app(Settings(data_dir=data_dir, scheduler_enabled=False))

Built from the app rather than written by hand, so the schema cannot describe a response the code
does not return. The callable decides what building it needs; the scratch directory keeps keys or
databases the app creates on startup out of a real deployment.

The keys are sorted, and ``info.version`` is fixed at 0.0.0: the committed schema describes the
API's shape, not a release, so it does not change with every version or with whichever version
happens to be installed.

Usage: .devtools/bin/export-openapi.py [--config devtools.toml]   (with the app's interpreter)
"""

from __future__ import annotations

import argparse
import importlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


class ExportError(Exception):
    """A problem finding or building the app, reported as one line."""


def app_reference(config: str) -> str:
    """Read ``openapi.app`` through the config reader beside this script.

    Args:
        config: Path to devtools.toml.

    Returns:
        The ``module:callable`` reference.

    Raises:
        ExportError: If the setting is missing or invalid.
    """
    reader = Path(__file__).with_name("devtools-config.py")
    result = subprocess.run(
        [sys.executable, str(reader), "--config", config, "openapi.app"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ExportError(result.stderr.strip().removeprefix("devtools-config: "))
    return result.stdout.strip()


def load_builder(reference: str):
    """Import the callable a ``module:callable`` reference names.

    Args:
        reference: Such as ``myapp.api.schema:build_app``.

    Returns:
        The callable.

    Raises:
        ExportError: If the reference is malformed or does not resolve to a callable.
    """
    module_name, colon, attribute = reference.partition(":")
    if not colon or not module_name or not attribute:
        raise ExportError(f"openapi.app must be module:callable, not {reference!r}")
    try:
        module = importlib.import_module(module_name)
    except ImportError as e:
        raise ExportError(f"cannot import {module_name}: {e}") from None
    builder = getattr(module, attribute, None)
    if not callable(builder):
        raise ExportError(f"{module_name} has no callable {attribute}")
    return builder


def schema(builder) -> dict:
    """Build the app in a scratch directory and return its schema with the version fixed.

    Args:
        builder: The callable that builds the app from a data directory.

    Returns:
        The OpenAPI document.
    """
    with tempfile.TemporaryDirectory() as scratch:
        document = builder(Path(scratch)).openapi()
    document.setdefault("info", {})["version"] = "0.0.0"
    return document


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point.

    Args:
        argv: Arguments without the program name; defaults to sys.argv[1:].

    Returns:
        The exit status: 0 with the schema on stdout, 1 with the reason on stderr.
    """
    parser = argparse.ArgumentParser(description="Print the app's OpenAPI schema.")
    parser.add_argument("--config", default="devtools.toml", help="the devtools.toml to read")
    args = parser.parse_args(argv)
    try:
        document = schema(load_builder(app_reference(args.config)))
    except ExportError as e:
        print(f"export-openapi: {e}", file=sys.stderr)
        return 1
    json.dump(document, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
