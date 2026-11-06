#!/usr/bin/env python3
"""Turn the [ci] section of devtools.toml into the jobs that python-docker-app.yml runs.

Every job that tests or checks something is a suite, and every image the repository publishes is
an image entry:

    [ci]
    junit = ["backend/junit/*.xml"]          # optional: JUnit reports for Codecov
    coverage_description = "Coverage report" # optional: the commit status the report links from

    [[ci.suite]]
    name = "backend"                         # letters, digits, . _ -; unique
    python = true                            # set up Python ([ci] python, default 3.14)
    node = false                             # set up Node ([ci] node, default 24)
    cache = "~/apt-cache"                    # optional: a directory kept between runs
    setup = "bin/install-ocr.sh ~/apt-cache" # optional, run first
    install = 'pip install -e "backend[test]"'
    run = "bin/test-backend.sh"              # required
    env = { PYTHON = "python" }              # optional
    coverage = ["backend/coverage.json", "backend/htmlcov"]  # optional: kept for the coverage job
    timeout = 30                             # optional, minutes

    [[ci.image]]
    image = "ghcr.io/jmerhar/myapp"          # required
    context = "."                            # optional, the default
    dockerfile = "Dockerfile"                # optional: relative to the repository root;
                                             # defaults to <context>/Dockerfile
    paths = ["backend/"]                     # optional: build only when one of these, the
                                             # dockerfile, devtools.toml or a workflow changed

Images share the settings that go with how they are deployed:

    [ci]
    image_tags = "release"        # "release": edge, the full SHA, and a version's three tags;
                                  # "latest": the short SHA and latest
    revision_arg = "REVISION"     # the build argument given the commit SHA ("" for none)
    provenance = true             # a provenance attestation on pushed images
    images_on_pull_request = true # build a pull request's images, without pushing them
    github_release = true         # on a version tag, publish its CHANGELOG.md section

A repository with a coverage.toml must keep at least one suite's coverage, so the gate it
configures always runs, and the section must declare at least one suite or image.

Commands:

    ci.py plan --event EVENT --ref REF --default-branch BRANCH [--since SHA]
                    print the workflow's plan as GITHUB_OUTPUT lines
    ci.py env       append CI_SUITE's env to $GITHUB_ENV
    ci.py pack      pack CI_SUITE's coverage files into coverage-<name>.tgz
    ci.py unpack DIR
                    unpack every coverage-*.tgz in DIR into the repository

Images are pushed only from the default branch and from tags; anything else builds them without
pushing, so an unmerged branch never replaces a published tag.

--since names the commit the event's changes are measured from: a push's previous head or a pull
request's base. An image is built when the tree differs from that commit's in one of its paths,
which also covers a force-push. A tag, a manual or scheduled run, or a since that git does not
know builds every image. A push only measures what it adds, so an image whose change landed in a
run that failed is built by the next run that touches its paths, or by a manual run.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tarfile
import uuid
from pathlib import Path

NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")
ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# Changes that may alter how every image is built.
EVERY_IMAGE = (".github/workflows/", "devtools.toml")
# A URL carrying a password, which the runner masks wherever it appears; a job output holding one
# is dropped, so the plan would lose its suites.
URL_CREDENTIALS = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^/\s@]*:[^/\s@]*@")
# Variables a step cannot set through $GITHUB_ENV, which the runner refuses or owns.
RESERVED_ENV = re.compile(r"(GITHUB_|RUNNER_).*|NODE_OPTIONS|CI")

CI_KEYS = {
    "python": str,
    "node": str,
    "junit": list,
    "coverage_description": str,
    "image_tags": str,
    "revision_arg": str,
    "provenance": bool,
    "images_on_pull_request": bool,
    "github_release": bool,
    "suite": list,
    "image": list,
}
SUITE_KEYS = {
    "name": str,
    "python": bool,
    "node": bool,
    "cache": str,
    "setup": str,
    "install": str,
    "run": str,
    "env": dict,
    "coverage": list,
    "timeout": int,
}
IMAGE_KEYS = {"image": str, "context": str, "dockerfile": str, "paths": list}
TAGS = {
    "release": [
        "type=edge",
        "type=sha,format=long",
        "type=semver,pattern={{version}}",
        "type=semver,pattern={{major}}.{{minor}}",
        "type=semver,pattern={{major}}",
    ],
    "latest": ["type=sha", "type=raw,value=latest"],
}


class CIError(Exception):
    """A problem with the [ci] section or with what a command was asked to do."""


def check_keys(table: dict, allowed: dict, where: str) -> None:
    """Refuse unknown keys and values of the wrong type.

    Args:
        table: The TOML table.
        allowed: Each allowed key and the type its value must have.
        where: How to name the table in an error.

    Raises:
        CIError: On an unknown key or a value of the wrong type.
    """
    unknown = sorted(set(table) - set(allowed))
    if unknown:
        raise CIError(f"{where} has unknown keys: {', '.join(unknown)}")
    for key, value in table.items():
        kind = allowed[key]
        # bool is a subclass of int, so a boolean is refused where a number is expected.
        if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
            raise CIError(f"{where} {key} must be a {kind.__name__}")


def strings(values: list, where: str) -> list[str]:
    """Check that a list holds only strings."""
    if not all(isinstance(v, str) for v in values):
        raise CIError(f"{where} must list strings")
    return values


def load(path: str = "devtools.toml") -> dict:
    """Read and check the [ci] section, filling in every default.

    Args:
        path: The configuration file.

    Returns:
        The section, with each suite and image complete.

    Raises:
        CIError: If the file is missing or invalid, or the section is malformed.
    """
    # Imported here, so the commands that run under a suite's own Python need no tomllib.
    try:
        import tomllib
    except ImportError:  # pragma: no cover - only reached on Python 3.10 and older
        raise CIError("Python 3.11 or newer is required to read devtools.toml") from None
    try:
        with open(path, "rb") as f:
            ci = tomllib.load(f).get("ci")
    except FileNotFoundError:
        raise CIError(f"no {path}; run this from the repository root") from None
    except tomllib.TOMLDecodeError as e:
        raise CIError(f"{path} is not valid TOML: {e}") from None
    if ci is None:
        raise CIError(f"{path} has no [ci] section")
    if not isinstance(ci, dict):
        raise CIError(f"ci in {path} must be a table")
    check_keys(ci, CI_KEYS, "[ci]")
    plan = {
        "python": ci.get("python", "3.14"),
        "node": ci.get("node", "24"),
        "junit": strings(ci.get("junit", []), "[ci] junit"),
        "coverage_description": ci.get("coverage_description", "Coverage report"),
        "image_tags": ci.get("image_tags", "release"),
        "revision_arg": ci.get("revision_arg", "REVISION"),
        "provenance": ci.get("provenance", True),
        "images_on_pull_request": ci.get("images_on_pull_request", True),
        "github_release": ci.get("github_release", True),
    }
    if plan["image_tags"] not in TAGS:
        raise CIError(f"[ci] image_tags must be one of {', '.join(TAGS)}")
    if plan["revision_arg"] and not ENV_NAME.fullmatch(plan["revision_arg"]):
        raise CIError("[ci] revision_arg must be a build argument name")
    plan["suites"] = [suite(s, n) for n, s in enumerate(ci.get("suite", []), 1)]
    names = [s["name"] for s in plan["suites"]]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise CIError(f"[[ci.suite]] names must be unique: {', '.join(duplicates)}")
    plan["images"] = [image(i, n) for n, i in enumerate(ci.get("image", []), 1)]
    if not plan["suites"] and not plan["images"]:
        raise CIError(f"[ci] in {path} declares no [[ci.suite]] and no [[ci.image]]")
    coverage_toml = Path(path).with_name("coverage.toml")
    if coverage_toml.is_file() and not any(s["coverage"] for s in plan["suites"]):
        raise CIError(
            f"{coverage_toml.name} sets coverage gates, but no [[ci.suite]] keeps coverage reports"
        )
    return plan


def suite(table: object, n: int) -> dict:
    """Check one [[ci.suite]] table and fill in its defaults."""
    where = f"[[ci.suite]] {n}"
    if not isinstance(table, dict):
        raise CIError(f"{where} must be a table")
    check_keys(table, SUITE_KEYS, where)
    name = table.get("name")
    if name is None or not NAME.fullmatch(name):
        raise CIError(f"{where} needs a name of letters, digits, '.', '_' and '-'")
    if not table.get("run"):
        raise CIError(f"[[ci.suite]] {name} needs a run command")
    env = table.get("env", {})
    for key, value in env.items():
        if not ENV_NAME.fullmatch(key) or not isinstance(value, str):
            raise CIError(f"[[ci.suite]] {name} env must map variable names to strings")
        if RESERVED_ENV.fullmatch(key):
            raise CIError(f"[[ci.suite]] {name} env cannot set {key}, which the runner reserves")
        if "\n" in value or "\r" in value:
            raise CIError(f"[[ci.suite]] {name} env {key} must be one line")
    coverage = strings(table.get("coverage", []), f"[[ci.suite]] {name} coverage")
    if not all(relative(entry) for entry in coverage):
        raise CIError(f"[[ci.suite]] {name} coverage must name paths inside the repository")
    timeout = table.get("timeout", 30)
    if timeout < 1:
        raise CIError(f"[[ci.suite]] {name} timeout must be a positive number of minutes")
    for key in ("setup", "install", "run"):
        if URL_CREDENTIALS.search(table.get(key, "")):
            raise CIError(credentials_error(name, key))
    for key, value in env.items():
        if URL_CREDENTIALS.search(value):
            raise CIError(credentials_error(name, f"env {key}"))
    return {
        "name": name,
        "python": table.get("python", False),
        "node": table.get("node", False),
        "cache": table.get("cache", ""),
        "setup": table.get("setup", ""),
        "install": table.get("install", ""),
        "run": table["run"],
        "env": env,
        "coverage": coverage,
        "timeout": timeout,
    }


def credentials_error(name: str, where: str) -> str:
    """Explain why a URL with a password cannot appear in a suite."""
    return (
        f"[[ci.suite]] {name} {where} holds a URL with a password, which GitHub masks, dropping "
        "the plan that carries it; have the setup command write it to $GITHUB_ENV instead"
    )


def relative(path: str) -> bool:
    """Whether a path stays inside the repository: not absolute, and no `..`."""
    return bool(path) and not path.startswith("/") and ".." not in Path(path).parts


def prefix(path: str) -> str:
    """A configured path as git prints it: no leading ./ and no trailing slash."""
    return path.removeprefix("./").rstrip("/")


def image(table: object, n: int) -> dict:
    """Check one [[ci.image]] table and fill in its defaults."""
    where = f"[[ci.image]] {n}"
    if not isinstance(table, dict):
        raise CIError(f"{where} must be a table")
    check_keys(table, IMAGE_KEYS, where)
    if not table.get("image"):
        raise CIError(f"{where} needs an image")
    context = table.get("context", ".")
    dockerfile = table.get("dockerfile", f"{context.rstrip('/')}/Dockerfile")
    paths = strings(table.get("paths", []), f"{where} paths")
    if not all(relative(p) for p in paths):
        raise CIError(f"{where} paths must name paths inside the repository")
    if paths:
        # The image's own Dockerfile is part of what it is built from.
        paths = [*paths, dockerfile]
    return {"image": table["image"], "context": context, "dockerfile": dockerfile, "paths": paths}


def changed_files(since: str | None) -> list[str] | None:
    """The files whose content differs between a commit's tree and HEAD's.

    A tree comparison rather than the commits in between, so a force-push counts everything the
    new head has that the old one's images were built without. Renames are listed as a deletion
    and an addition, so both sides count, and names come unquoted.

    Args:
        since: The commit to compare with, or None.

    Returns:
        The changed paths, or None when every image should be built: no commit to compare with,
        or one git does not know.
    """
    if not since or set(since) == {"0"}:
        return None
    result = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", "-z", since, "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return [path for path in result.stdout.split("\0") if path]


def wanted(entry: dict, changed: list[str] | None) -> bool:
    """Whether an image is built for a set of changes."""
    if changed is None or not entry["paths"]:
        return True
    shared = [prefix(p) for p in EVERY_IMAGE]
    prefixes = [prefix(p) for p in entry["paths"]] + shared
    return any(path == p or path.startswith(p + "/") for path in changed for p in prefixes)


def output_lines(values: dict[str, str]) -> str:
    """Render values as GITHUB_OUTPUT lines, with a delimiter for any that span lines."""
    lines = []
    for key, value in values.items():
        if "\n" in value:
            delimiter = f"EOF_{uuid.uuid4().hex}"
            lines += [f"{key}<<{delimiter}", value, delimiter]
        else:
            lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"


def plan(
    config: dict, event: str, since: str | None, ref: str = "", default_branch: str = ""
) -> dict[str, str]:
    """Work out what the workflow runs for an event.

    Args:
        config: The checked [ci] section.
        event: The GitHub event name.
        since: The commit the event's changes are measured from, if any.
        ref: The ref the run is for, such as refs/heads/main or refs/tags/v1.2.3.
        default_branch: The repository's default branch.

    Returns:
        The workflow's outputs, as strings.
    """
    pull_request = event.startswith("pull_request")
    tag = ref.startswith("refs/tags/")
    on_default = bool(default_branch) and ref == f"refs/heads/{default_branch}"
    push = not pull_request and (tag or on_default)
    images = []
    if config["images"] and not (pull_request and not config["images_on_pull_request"]):
        every = tag or event in {"workflow_dispatch", "schedule"}
        changed = None if every else changed_files(since)
        images = [i for i in config["images"] if wanted(i, changed)]
    for entry in images:
        del entry["paths"]
    build_args = ""
    if config["revision_arg"]:
        build_args = f"{config['revision_arg']}={os.environ.get('GITHUB_SHA', '')}"
    return {
        "python": config["python"],
        "node": config["node"],
        "suites": json.dumps(config["suites"]),
        "has_suites": json.dumps(bool(config["suites"])),
        "coverage": json.dumps(any(s["coverage"] for s in config["suites"])),
        "junit": ",".join(config["junit"]),
        "coverage_description": config["coverage_description"],
        "images": json.dumps(images),
        "has_images": json.dumps(bool(images)),
        "push": json.dumps(push),
        "tags": "\n".join(TAGS[config["image_tags"]]),
        "build_args": build_args,
        "provenance": json.dumps(config["provenance"]),
        "github_release": json.dumps(config["github_release"]),
    }


def current_suite() -> dict:
    """The suite the workflow passes in CI_SUITE, as JSON."""
    raw = os.environ.get("CI_SUITE")
    if not raw:
        raise CIError("CI_SUITE is not set; the workflow passes the suite as JSON")
    return json.loads(raw)


def write_env(entry: dict) -> str:
    """Render a suite's env as GITHUB_ENV lines."""
    return "".join(f"{key}={value}\n" for key, value in entry.get("env", {}).items())


def _without_symlinks(member: tarfile.TarInfo) -> tarfile.TarInfo | None:
    """Leave symbolic links out of an archive.

    A report's symbolic links (kcov keeps one per traced script, pointing into its own output by
    absolute path) are shortcuts no report reads, and one can point outside the repository, which
    unpacking refuses. Hard links stay: they name files inside the archive.
    """
    return None if member.issym() else member


def pack(entry: dict, root: Path) -> Path:
    """Pack a suite's coverage files, keeping their paths from the repository root.

    Args:
        entry: The suite.
        root: The repository root.

    Returns:
        The archive written.

    Raises:
        CIError: If a coverage path does not exist, since a missing report would otherwise pass
            silently until the gate finds nothing to measure.
    """
    missing = [p for p in entry["coverage"] if not (root / p).exists()]
    if missing:
        raise CIError(f"suite {entry['name']} left no {', '.join(missing)}")
    archive = root / f"coverage-{entry['name']}.tgz"
    with tarfile.open(archive, "w:gz") as tar:
        for path in entry["coverage"]:
            tar.add(root / path, arcname=path, filter=_without_symlinks)
    return archive


def unpack(directory: Path, root: Path) -> list[str]:
    """Unpack every coverage archive in a directory into the repository root.

    Args:
        directory: Where the coverage job downloaded the archives.
        root: The repository root.

    Returns:
        The archives unpacked, by name.
    """
    unpacked = []
    for archive in sorted(directory.rglob("coverage-*.tgz")):
        with tarfile.open(archive) as tar:
            tar.extractall(root, filter="data")
        unpacked.append(archive.name)
    return unpacked


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point; see the module docstring."""
    parser = argparse.ArgumentParser(description="Plan and support devtools' CI workflow.")
    parser.add_argument("--config", default="devtools.toml")
    commands = parser.add_subparsers(dest="command", required=True)
    planner = commands.add_parser("plan")
    planner.add_argument("--event", required=True)
    planner.add_argument("--ref", required=True)
    planner.add_argument("--default-branch", required=True)
    planner.add_argument("--since", default=None)
    commands.add_parser("env")
    commands.add_parser("pack")
    commands.add_parser("unpack").add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    root = Path.cwd()
    try:
        if args.command == "plan":
            config = load(args.config)
            values = plan(config, args.event, args.since, args.ref, args.default_branch)
            sys.stdout.write(output_lines(values))
        elif args.command == "env":
            target = os.environ.get("GITHUB_ENV")
            if not target:
                raise CIError("GITHUB_ENV is not set; this runs inside a workflow")
            with open(target, "a", encoding="utf-8") as f:
                f.write(write_env(current_suite()))
        elif args.command == "pack":
            print(f"ci: packed {pack(current_suite(), root).name}")
        else:
            names = unpack(args.directory, root)
            print(f"ci: unpacked {', '.join(names) if names else 'no coverage archives'}")
    except CIError as e:
        print(f"ci: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
