#!/usr/bin/env python3
"""Check that a repository is in step with devtools, and write the files devtools generates.

    devtools-check.py          report every check that fails, and exit 1 if any does
    devtools-check.py --fix    write .github/dependabot.yml and codecov.yml as generated, then check

The checks:

- The vendored fetcher matches the one at the ref devtools.toml pins, which the fetcher puts in
  .devtools/fetch/devtools-fetch.sh when [fetch] files lists "fetch/devtools-fetch.sh".
- .github/dependabot.yml is what the [dependabot] table generates: GitHub Actions, then each
  update listed, every one taking a release only once it is three days old, apart from the
  packages released from the same hands. Each update's minor and patch releases arrive as one
  weekly pull request, and its majors as another, named after the group with "-majors" added,
  which waits for a hand migration. Security updates are not grouped either way.
- codecov.yml, when there is a coverage.toml, is what it generates: informational statuses, no
  comment, and one carried-forward flag per suite.
- The ruff configuration, when there is one, extends the shared base.
- With an [npm] table, the Makefile installs packages through make/npm.mk's node-modules rather
  than a bare `npm install`, which writes the registry it reached into the lockfile; and listing
  make/npm.mk in [fetch] files also lists the scripts its targets run.

    [check]
    fetcher = "bin/devtools-fetch.sh"   # optional: where the fetcher is vendored; "" for none
    ruff_base = ".devtools/config/ruff.toml"  # optional: the base the ruff configuration extends

    [[dependabot.update]]
    ecosystem = "npm"                   # npm, pip, gradle, docker, ...
    directory = "/frontend"             # or directories = [...], for one pull request over several
    group = "frontend"                  # optional, the default is the ecosystem's name
    comment = "The interface."          # optional, written above the entry
    update_types = ["minor", "patch"]   # optional: what the group takes (the default); the rest
                                        # go to the "-majors" group, which exists unless the
                                        # group takes majors itself
    cooldown = 3                        # optional, days; 0 for none
    cooldown_exclude = ["jigkit"]       # optional; defaults by ecosystem (see COOLDOWN_EXCLUDE)
    ignore = [{ dependency = "typescript", update_types = ["version-update:semver-major"] }]

    [codecov]
    paths = { backend = ["backend/"] }  # optional: the files each suite's flag covers
    fixes = ["/src/::"]                 # optional: path rewrites, for reports measured elsewhere

Usage: .devtools/bin/devtools-check.py [--fix]    (from the repository root)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DEPENDABOT = ".github/dependabot.yml"
CODECOV = "codecov.yml"
FETCHED_FETCHER = ".devtools/fetch/devtools-fetch.sh"
RUFF_BASE = ".devtools/config/ruff.toml"
#: The packages released from the same hands, taken as soon as they are out.
COOLDOWN_EXCLUDE = {"pip": ["jigkit"], "npm": ["@jmerhar/*"]}
UPDATE_KEYS = {
    "ecosystem": str,
    "directory": str,
    "directories": list,
    "group": str,
    "comment": str,
    "update_types": list,
    "cooldown": int,
    "cooldown_exclude": list,
    "ignore": list,
}
IGNORE_KEYS = {"dependency": str, "update_types": list}
#: What a group takes unless its update says otherwise; majors go to a group of their own.
GROUP_UPDATE_TYPES = ["minor", "patch"]
UPDATE_TYPES = {"major", "minor", "patch"}
#: Appended to a group's name for the group of its majors.
MAJORS_SUFFIX = "-majors"
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
#: The scripts make/npm.mk's targets run.
NPM_MK_FILES = ["bin/npm-ci.sh", "bin/lockfile.sh", "bin/check-lockfile.sh"]
#: An npm command that resolves packages afresh and rewrites the lockfile.
NPM_INSTALL = re.compile(r"\bnpm\s+(install|i|add)\b")


class CheckError(Exception):
    """A problem with devtools.toml, reported as one line."""


def load(root: Path) -> dict:
    """Read devtools.toml and coverage.toml from a repository root.

    Args:
        root: The repository root.

    Returns:
        {"devtools": ..., "coverage": ... or None}.

    Raises:
        CheckError: If devtools.toml is missing or either file is invalid.
    """
    import tomllib

    def read(path: Path) -> dict:
        try:
            with open(path, "rb") as f:
                return tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise CheckError(f"{path.name} is not valid TOML: {e}") from None

    if not (root / "devtools.toml").is_file():
        raise CheckError("no devtools.toml; run this from the repository root")
    coverage = root / "coverage.toml"
    return {
        "devtools": read(root / "devtools.toml"),
        "coverage": read(coverage) if coverage.is_file() else None,
    }


def quote(value: str) -> str:
    """A YAML double-quoted scalar."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def comment_lines(text: str, indent: str) -> list[str]:
    """A comment, one `#` line per line of text."""
    return [f"{indent}# {line}".rstrip() for line in text.splitlines()]


def check_table(table: object, allowed: dict, where: str) -> dict:
    """Refuse a value that is not a table, an unknown key, or a value of the wrong type."""
    if not isinstance(table, dict):
        raise CheckError(f"{where} must be a table")
    unknown = sorted(set(table) - set(allowed))
    if unknown:
        raise CheckError(f"{where} has unknown keys: {', '.join(unknown)}")
    for key, value in table.items():
        kind = allowed[key]
        if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
            raise CheckError(f"{where} {key} must be a {kind.__name__}")
    return table


def updates(config: dict) -> list[dict]:
    """The Dependabot updates: GitHub Actions first, then each [[dependabot.update]], checked."""
    table = config.get("dependabot", {})
    check_table(table, {"update": list}, "[dependabot]")
    entries = [{"ecosystem": "github-actions", "directory": "/", "group": "actions"}]
    for n, entry in enumerate(table.get("update", []), 1):
        where = f"[[dependabot.update]] {n}"
        check_table(entry, UPDATE_KEYS, where)
        if not entry.get("ecosystem"):
            raise CheckError(f"{where} needs a ecosystem")
        if bool(entry.get("directory")) == bool(entry.get("directories")):
            raise CheckError(f"{where} needs a directory or directories, not both")
        if not NAME.fullmatch(entry.get("group", entry["ecosystem"])):
            raise CheckError(f"{where} group must be letters, digits, '-' and '_'")
        if entry.get("cooldown", 3) < 0:
            raise CheckError(f"{where} cooldown must be a number of days")
        for ignore in entry.get("ignore", []):
            check_table(ignore, IGNORE_KEYS, f"{where} ignore")
            if not ignore.get("dependency"):
                raise CheckError(f"{where} ignore needs a dependency")
            if not all(isinstance(v, str) for v in ignore.get("update_types", [])):
                raise CheckError(f"{where} ignore update_types must list strings")
        for key in ("update_types", "cooldown_exclude", "directories"):
            if not all(isinstance(v, str) for v in entry.get(key, [])):
                raise CheckError(f"{where} {key} must list strings")
        types = entry.get("update_types", GROUP_UPDATE_TYPES)
        if not types or not set(types) <= UPDATE_TYPES:
            raise CheckError(f"{where} update_types must list major, minor or patch")
        entries.append(entry)
    seen = set()
    for entry in entries:
        for directory in entry.get("directories") or [entry["directory"]]:
            key = (entry["ecosystem"], directory)
            if key in seen:
                raise CheckError(f"dependabot lists {entry['ecosystem']} in {directory} twice")
            seen.add(key)
    return entries


def dependabot(config: dict) -> str:
    """Generate .github/dependabot.yml from devtools.toml's [dependabot] table."""
    lines = [
        "# Generated by devtools-check.py --fix from devtools.toml's [dependabot] table: edit that",
        "# table rather than this file, which `devtools-check.py` compares with what it generates.",
        "#",
        "# Weekly updates: per ecosystem, one pull request of minor and patch releases and one",
        "# of majors, which waits for a hand migration. A release is taken once it is three days",
        "# old, so a hijacked version has usually been pulled before an update proposes it; the",
        "# packages released from the same hands are taken at once.",
        "version: 2",
        "updates:",
    ]
    for n, entry in enumerate(updates(config)):
        ecosystem = entry["ecosystem"]
        if n:
            lines.append("")
        if entry.get("comment"):
            lines += comment_lines(entry["comment"], "  ")
        lines.append(f"  - package-ecosystem: {quote(ecosystem)}")
        if entry.get("directories"):
            lines.append("    directories:")
            lines += [f"      - {quote(d)}" for d in entry["directories"]]
        else:
            lines.append(f"    directory: {quote(entry['directory'])}")
        lines += ["    schedule:", '      interval: "weekly"']
        days = entry.get("cooldown", 3)
        if days:
            lines += ["    cooldown:", f"      default-days: {days}"]
            exclude = entry.get("cooldown_exclude", COOLDOWN_EXCLUDE.get(ecosystem, []))
            if exclude:
                lines.append("      exclude:")
                lines += [f"        - {quote(name)}" for name in exclude]
        if entry.get("ignore"):
            lines.append("    ignore:")
            for ignore in entry["ignore"]:
                lines.append(f"      - dependency-name: {quote(ignore['dependency'])}")
                if ignore.get("update_types"):
                    types = ", ".join(quote(t) for t in ignore["update_types"])
                    lines.append(f"        update-types: [{types}]")
        group = entry.get("group", ecosystem)
        types = entry.get("update_types", GROUP_UPDATE_TYPES)
        groups = [(group, types)]
        if "major" not in types:
            groups.append((group + MAJORS_SUFFIX, ["major"]))
        lines.append("    groups:")
        for name, group_types in groups:
            lines += [
                f"      {name}:",
                "        patterns:",
                '          - "*"',
                "        update-types:",
            ]
            lines += [f"          - {quote(t)}" for t in group_types]
    return "\n".join(lines) + "\n"


def codecov(config: dict, coverage: dict) -> str:
    """Generate codecov.yml from coverage.toml's suites and devtools.toml's [codecov] table."""
    table = config.get("codecov", {})
    check_table(table, {"paths": dict, "fixes": list}, "[codecov]")
    paths = table.get("paths", {})
    fixes = table.get("fixes", [])
    if not all(isinstance(f, str) for f in fixes):
        raise CheckError("[codecov] fixes must list strings")
    suites = coverage.get("suites", {})
    unknown = sorted(set(paths) - set(suites))
    if unknown:
        raise CheckError(f"[codecov] paths names suites coverage.toml lacks: {', '.join(unknown)}")
    for suite, listed in paths.items():
        if not isinstance(listed, list) or not all(isinstance(p, str) for p in listed):
            raise CheckError(f"[codecov] paths {suite} must list paths")
    lines = [
        "# Generated by devtools-check.py --fix from coverage.toml and devtools.toml's [codecov]",
        "# table. Codecov is informational only: the gate that fails a build runs in CI, with its",
        "# thresholds in coverage.toml. Each suite uploads under its own flag.",
        "coverage:",
        "  status:",
        "    project:",
        "      default:",
        "        informational: true",
        "    patch:",
        "      default:",
        "        informational: true",
        "",
        "comment: false",
    ]
    if fixes:
        lines += ["", "fixes:"] + [f"  - {quote(f)}" for f in fixes]
    if suites:
        lines += ["", "flags:"]
        for suite in suites:
            lines.append(f"  {suite}:")
            if paths.get(suite):
                lines.append("    paths:")
                lines += [f"      - {p}" for p in paths[suite]]
            lines.append("    carryforward: true")
    return "\n".join(lines) + "\n"


def ruff_extends_base(root: Path, base: str = RUFF_BASE) -> str | None:
    """Why the ruff configuration does not extend the shared base, or None when it does or
    there is no ruff configuration."""
    import tomllib

    candidates = [root / "ruff.toml", root / ".ruff.toml"]
    candidates += sorted(root.glob("pyproject.toml")) + sorted(root.glob("*/pyproject.toml"))
    for path in candidates:
        if not path.is_file():
            continue
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as e:
            raise CheckError(f"{path.relative_to(root)} is not valid TOML: {e}") from None
        table = data if path.name.endswith("ruff.toml") else data.get("tool", {}).get("ruff")
        if table is None:
            continue
        extend = table.get("extend", "")
        resolved = (path.parent / extend).resolve() if extend else None
        if resolved != (root / base).resolve():
            return f"{path.relative_to(root)} does not extend {base}"
    return None


def npm_problems(root: Path, config: dict) -> list[str]:
    """Why the repository's npm setup is not the shared one, a line per problem.

    Args:
        root: The repository root.
        config: devtools.toml.

    Returns:
        A line for each Makefile line that runs a bare `npm install` while devtools.toml has an
        [npm] table, and one for each script make/npm.mk needs that [fetch] files leaves out.
    """
    problems = []
    files = config.get("fetch", {}).get("files", [])
    if "make/npm.mk" in files:
        missing = [f for f in NPM_MK_FILES if f not in files]
        if missing:
            problems.append(f"make/npm.mk needs {', '.join(missing)} in [fetch] files")
    makefile = root / "Makefile"
    if "npm" in config and makefile.is_file():
        for n, line in enumerate(makefile.read_text(encoding="utf-8").splitlines(), 1):
            if NPM_INSTALL.search(line.split("#", 1)[0]):
                problems.append(
                    f"Makefile:{n} runs npm install, which writes the registry it reaches into "
                    "the lockfile; run `$(MAKE) node-modules` from make/npm.mk"
                )
    return problems


def checks(root: Path, fix: bool = False) -> list[str]:
    """Run every check, writing the generated files first when fix is set.

    Args:
        root: The repository root.
        fix: Whether to write .github/dependabot.yml and codecov.yml.

    Returns:
        A line for each check that fails.
    """
    files = load(root)
    config = files["devtools"]
    problems = []

    table = check_table(config.get("check", {}), {"fetcher": str, "ruff_base": str}, "[check]")
    fetcher = table.get("fetcher", "bin/devtools-fetch.sh")
    vendored = root / fetcher
    fetched = root / FETCHED_FETCHER
    if not fetcher:
        pass
    elif not vendored.is_file():
        problems.append(f"no fetcher at {vendored.relative_to(root)}; set [check] fetcher")
    elif not fetched.is_file():
        problems.append(
            'add "fetch/devtools-fetch.sh" to [fetch] files, so the fetcher can be compared'
        )
    elif vendored.read_bytes() != fetched.read_bytes():
        problems.append(
            f"{vendored.relative_to(root)} differs from the fetcher at the pinned ref; "
            f"copy {FETCHED_FETCHER} over it"
        )

    generated = {DEPENDABOT: dependabot(config)}
    if files["coverage"] is not None:
        generated[CODECOV] = codecov(config, files["coverage"])
    for path, text in generated.items():
        target = root / path
        if fix:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        current = target.read_text(encoding="utf-8") if target.is_file() else None
        if current != text:
            problems.append(
                f"{path} is not what devtools.toml generates; run devtools-check.py --fix"
            )

    ruff = ruff_extends_base(root, table.get("ruff_base", RUFF_BASE))
    if ruff:
        problems.append(ruff)
    problems += npm_problems(root, config)
    return problems


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point; see the module docstring."""
    parser = argparse.ArgumentParser(description="Check a repository against devtools.")
    parser.add_argument("--fix", action="store_true", help="write the generated files first")
    args = parser.parse_args(argv)
    try:
        problems = checks(Path.cwd(), args.fix)
    except CheckError as e:
        print(f"devtools-check: {e}", file=sys.stderr)
        return 1
    for problem in problems:
        print(f"devtools-check: {problem}", file=sys.stderr)
    if problems:
        return 1
    print("devtools-check: in step with devtools")
    return 0


if __name__ == "__main__":
    sys.exit(main())
