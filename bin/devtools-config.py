#!/usr/bin/env python3
"""Print one value from devtools.toml, in a form a shell script can read line by line.

The fetched scripts read their settings through this, so devtools.toml is parsed in one place and
every missing or mistyped key is reported the same way. A key names a table and a key in it,
separated by a dot:

    [compose]
    stacks = [["docker-compose.yml"], ["docker-compose.yml", "docker-compose.build.yml"]]

    $ devtools-config.py compose.stacks
    docker-compose.yml
    docker-compose.yml<TAB>docker-compose.build.yml

A string or number prints as it is and a boolean as true or false. A list prints one item per line,
and a list of lists one inner list per line, tab-separated. Each --default supplies a line to print
when the key is absent; without one, an absent key is an error naming the key. --shape list or
--shape lists requires the value to be a list of scalars, or a list of non-empty lists of them.

Usage: devtools-config.py [--config FILE] [--shape list|lists] [--default VALUE]... TABLE.KEY
"""

from __future__ import annotations

import argparse
import sys

try:
    import tomllib
except ImportError:  # pragma: no cover - only reached on Python 3.10 and older
    found = sys.version.split()[0]
    sys.exit(f"Python 3.11 or newer is required to read devtools.toml; found {found}")


class ConfigError(Exception):
    """A problem with devtools.toml or the key asked for, reported as one line."""


def scalar(value: object, key: str) -> str:
    """Render one scalar for the shell, refusing anything a line cannot carry.

    Args:
        value: A value read from the TOML document.
        key: The dotted key it came from, for the error message.

    Returns:
        The value as a single line of text.

    Raises:
        ConfigError: If the value is a table, contains a newline or tab, or is not a scalar.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, str):
        if "\n" in value or "\t" in value:
            raise ConfigError(f"{key} holds a newline or tab, which a shell cannot read back")
        return value
    raise ConfigError(f"{key} must hold strings, numbers or booleans, or lists of them")


def render(value: object, key: str) -> list[str]:
    """Turn a configuration value into the lines printed for it.

    Args:
        value: The value of the key.
        key: The dotted key, for error messages.

    Returns:
        One line per item: a scalar is one line, a list one line per item, and a list of lists one
        tab-separated line per inner list.

    Raises:
        ConfigError: If the value nests deeper than a list of lists, or holds a table.
    """
    if not isinstance(value, list):
        return [scalar(value, key)]
    lines = []
    for item in value:
        if isinstance(item, list):
            lines.append("\t".join(scalar(v, key) for v in item))
        else:
            lines.append(scalar(item, key))
    return lines


def check_shape(value: object, key: str, shape: str | None) -> None:
    """Refuse a value that does not have the shape a script expects.

    Args:
        value: The value of the key.
        key: The dotted key, for the error message.
        shape: None for anything, "list" for a list of scalars, or "lists" for a list of non-empty
            lists of scalars.

    Raises:
        ConfigError: If the value has another shape.
    """
    if shape == "list" and (not isinstance(value, list) or any(isinstance(v, list) for v in value)):
        raise ConfigError(f'{key} must be a list, such as ["a", "b"]')
    if shape == "lists" and (
        not isinstance(value, list) or not all(isinstance(v, list) and v for v in value)
    ):
        raise ConfigError(f'{key} must be a list of non-empty lists, such as [["a"], ["a", "b"]]')


def lookup(path: str, key: str, defaults: list[str] | None, shape: str | None = None) -> list[str]:
    """Read devtools.toml and return the lines for one key.

    Args:
        path: The configuration file.
        key: TABLE.KEY to read.
        defaults: Lines to return when the key is absent, or None if it is required.
        shape: The shape the value must have, as check_shape takes it.

    Returns:
        The lines to print.

    Raises:
        ConfigError: If the file is missing or invalid, the key is malformed, or a required key is
            absent.
    """
    table_name, dot, name = key.partition(".")
    if not dot or not table_name or not name or "." in name:
        raise ConfigError(f"{key!r} is not TABLE.KEY")
    try:
        with open(path, "rb") as f:
            document = tomllib.load(f)
    except FileNotFoundError:
        raise ConfigError(f"no {path}; run this from the repository root") from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path} is not valid TOML: {e}") from None
    table = document.get(table_name, {})
    if not isinstance(table, dict):
        raise ConfigError(f"{table_name} in {path} must be a table")
    if name not in table:
        if defaults is None:
            raise ConfigError(f"{path} sets no {key}; add {name} to its [{table_name}] table")
        return defaults
    check_shape(table[name], key, shape)
    return render(table[name], key)


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point.

    Args:
        argv: Arguments without the program name; defaults to sys.argv[1:].

    Returns:
        The exit status: 0 on success, 1 when the value cannot be printed.
    """
    parser = argparse.ArgumentParser(description="Print one value from devtools.toml.")
    parser.add_argument("--config", default="devtools.toml", help="the file to read")
    parser.add_argument(
        "--default", action="append", help="a line to print when the key is absent (repeatable)"
    )
    parser.add_argument("--shape", choices=["list", "lists"], help="the shape the value must have")
    parser.add_argument("key", help="TABLE.KEY")
    args = parser.parse_args(argv)
    try:
        lines = lookup(args.config, args.key, args.default, args.shape)
    except ConfigError as e:
        print(f"devtools-config: {e}", file=sys.stderr)
        return 1
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
