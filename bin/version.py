#!/usr/bin/env python3
"""The release version, which every manifest, CHANGELOG.md and the compose file carry.

    version.py check [TAG]   every manifest names the same version, and the compose file pins each
                             image to that version's line (see `line`); with a tag (v1.2.3), that
                             the manifests name that version and CHANGELOG.md has its section
    version.py set X.Y.Z     write X.Y.Z, which must follow the current version, into every
                             manifest and its line into the compose file, and date CHANGELOG.md's
                             Unreleased section as X.Y.Z's; a release that cannot be cut changes
                             nothing
    version.py notes X.Y.Z   print X.Y.Z's section of CHANGELOG.md, without its heading

What carries the version is listed in devtools.toml:

    [version]
    pyprojects = ["backend/pyproject.toml"]   # each one's `version = "..."` line
    npm = ["frontend"]                        # package.json, and package-lock.json when present
    images = ["ghcr.io/jmerhar/myapp"]        # optional: images the compose file pins
    compose = "docker-compose.yml"            # optional, the default

Between releases a manifest may carry a development version (0.2.0.dev0), which counts as coming
before the release it names. npm only accepts semver, so package.json and its lockfile spell the
same version 0.2.0-dev.0. `--root DIR` works on a checkout other than the current directory.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

CHANGELOG = "CHANGELOG.md"
RELEASE = re.compile(r"\d+\.\d+\.\d+")
DEVELOPMENT = re.compile(r"(\d+\.\d+\.\d+)\.dev\d+")
NPM_DEVELOPMENT = re.compile(r"(\d+\.\d+\.\d+)-dev\.(\d+)")
UNRELEASED = "## Unreleased"
UNRELEASED_HEADING = re.compile(r"(?m)^## Unreleased$")
PYPROJECT_VERSION = re.compile(r'(?m)^(version = ")([^"]*)(")$')
#: package.json's version, and in package-lock.json both the top-level one and its root
#: package's; the dependencies' versions are left alone.
PACKAGE_VERSION = re.compile(r'(?m)^(  "version": ")([^"]*)(")')
LOCK_ROOT_VERSION = re.compile(
    r'(?m)^(    "": \{\n(?:      "name": "[^"]*",\n)?      "version": ")([^"]*)(")'
)


class VersionError(Exception):
    """What stops a check or a release, said to the person running it."""


@dataclass
class Layout:
    """Where a repository carries its version, as devtools.toml declares it."""

    #: Each manifest and the patterns of its own version lines.
    manifests: dict[str, list[re.Pattern[str]]] = field(default_factory=dict)
    images: list[str] = field(default_factory=list)
    compose: str = "docker-compose.yml"


def _config_reader():
    """Import devtools-config.py, which sits beside this script."""
    path = Path(__file__).with_name("devtools-config.py")
    spec = importlib.util.spec_from_file_location("devtools_config", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def layout(root: Path) -> Layout:
    """Read the [version] table of the repository's devtools.toml.

    Args:
        root: The repository root.

    Returns:
        The manifests, images and compose file to keep in step.

    Raises:
        VersionError: If devtools.toml is missing, invalid, or lists no manifest.
    """
    reader = _config_reader()
    path = str(root / "devtools.toml")
    try:
        pyprojects = reader.lookup(path, "version.pyprojects", [], "list")
        npm = reader.lookup(path, "version.npm", [], "list")
        images = reader.lookup(path, "version.images", [], "list")
        compose = reader.lookup(path, "version.compose", ["docker-compose.yml"])
    except reader.ConfigError as e:
        raise VersionError(str(e)) from None
    if len(compose) != 1:
        raise VersionError('version.compose must be one file, such as "docker-compose.yml"')
    [compose] = compose
    found = Layout(images=images, compose=compose)
    for pyproject in pyprojects:
        found.manifests[pyproject] = [PYPROJECT_VERSION]
    for directory in npm:
        found.manifests[f"{directory}/package.json"] = [PACKAGE_VERSION]
        lock = f"{directory}/package-lock.json"
        if (root / lock).is_file():
            found.manifests[lock] = [PACKAGE_VERSION, LOCK_ROOT_VERSION]
    if not found.manifests:
        raise VersionError("devtools.toml lists no manifests; set [version] pyprojects or npm")
    return found


def _read(root: Path, path: str) -> str:
    try:
        return (root / path).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise VersionError(f"{path} is missing") from None


def normalise(version: str) -> str:
    """The Python spelling of a version: npm's 0.2.0-dev.0 is 0.2.0.dev0."""
    npm = NPM_DEVELOPMENT.fullmatch(version)
    return f"{npm.group(1)}.dev{npm.group(2)}" if npm else version


def versions(root: Path, where: Layout) -> dict[str, str]:
    """Every manifest's version, by where it was found, in its Python spelling."""
    found = {}
    for path, patterns in where.manifests.items():
        text = _read(root, path)
        for n, pattern in enumerate(patterns):
            match = pattern.search(text)
            if match is None:
                raise VersionError(f"{path} names no version where one is expected")
            found[f"{path}#{n}" if n else path] = normalise(match.group(2))
    return found


def _order(version: str) -> tuple[int, ...]:
    """A key that sorts versions, a development version just before the release it names."""
    if RELEASE.fullmatch(version):
        return (*map(int, version.split(".")), 1)
    development = DEVELOPMENT.fullmatch(version)
    if development:
        return (*map(int, development.group(1).split(".")), 0)
    raise VersionError(f"{version} is neither a release like 1.2.3 nor a development version")


def line(version: str) -> str:
    """The image tag the compose file follows for `version`: its major, or before 1.0 its minor.

    A 0.x release may change anything, and an image builder publishes no bare major tag for one,
    so until 1.0 the compose file follows major.minor instead. A development version follows the
    release it leads up to.
    """
    development = DEVELOPMENT.fullmatch(version)
    major, minor, _ = (development.group(1) if development else version).split(".")
    return major if major != "0" else f"{major}.{minor}"


def _pins(text: str, where: Layout) -> list[tuple[int, re.Match[str]]]:
    """Each line of the compose file naming one of the images, read for its tag."""
    names = "|".join(re.escape(image) for image in where.images)
    ours = re.compile(rf"""^\s*image:\s*["']?(?:{names})(?:[:@"'\s]|$)""")
    # A tag followed by a digest is not a plain tag: a new version would keep the old digest.
    pin = re.compile(rf"""^(\s*image:\s*["']?(?:{names}):)([0-9A-Za-z._-]+)([^@]*)$""")
    pins = []
    # Split on newlines only, as set_version does when it rewrites the lines by number.
    for n, text_line in enumerate(text.split("\n")):
        if ours.match(text_line):
            match = pin.match(text_line)
            if match is None:
                raise VersionError(
                    f"{where.compose} line {n + 1} names an image without a plain tag"
                )
            pins.append((n, match))
    missing = [
        image for image in where.images if not any(image + ":" in m.group(1) for _, m in pins)
    ]
    if missing:
        raise VersionError(f"{where.compose} does not name {', '.join(missing)}")
    return pins


def check(root: Path, tag: str | None, where: Layout | None = None) -> str:
    """The version every manifest agrees on; with `tag`, also that it is the tag's, released."""
    where = where or layout(root)
    found = versions(root, where)
    if len(set(found.values())) != 1:
        listed = "\n".join(f"  {path}: {v}" for path, v in found.items())
        raise VersionError(f"the manifests name different versions:\n{listed}")
    version = next(iter(found.values()))
    _order(version)
    if where.images:
        expected = line(version)
        for _, pin in _pins(_read(root, where.compose), where):
            if pin.group(2) != expected:
                image = pin.group(1).split("image:")[1].strip().strip("\"'")
                raise VersionError(
                    f"{where.compose} pins {image}{pin.group(2)}, not {expected} as {version} is"
                )
    if tag is not None:
        if tag != f"v{version}":
            raise VersionError(f"the tag is {tag}, but the manifests name {version}")
        notes(root, version)
    return version


def set_version(root: Path, version: str, today: date) -> None:
    """Write `version` into every manifest and its line into the compose file, and date the
    Unreleased changelog section as it.

    Every file is worked out before any is written, so a release that cannot be cut changes
    nothing.
    """
    if not RELEASE.fullmatch(version):
        raise VersionError(f"{version} is not a version like 1.2.3")
    where = layout(root)
    current = check(root, None, where)
    if _order(version) <= _order(current):
        raise VersionError(f"{version} is not after {current}, the current version")
    text = _read(root, CHANGELOG)
    headings = UNRELEASED_HEADING.findall(text)
    if len(headings) != 1:
        found = "no" if not headings else "more than one"
        raise VersionError(f"{CHANGELOG} has {found} '{UNRELEASED}' section to release")
    if not any(
        line.strip() and not line.startswith("#")
        for line in _section(text, UNRELEASED).splitlines()
    ):
        raise VersionError(f"{CHANGELOG}'s '{UNRELEASED}' section is empty")
    if re.search(rf"(?m)^## {re.escape(version)}(\s|$)", text):
        raise VersionError(f"{CHANGELOG} already has a section for {version}")
    planned = {CHANGELOG: UNRELEASED_HEADING.sub(f"## {version} — {today.isoformat()}", text, 1)}
    # check() above found every pattern in its file, so each substitution has its line.
    for path, patterns in where.manifests.items():
        content = _read(root, path)
        for pattern in patterns:
            content = pattern.sub(rf"\g<1>{version}\g<3>", content, count=1)
        planned[path] = content
    if where.images:
        compose = _read(root, where.compose)
        lines = compose.split("\n")
        for n, pin in _pins(compose, where):
            lines[n] = f"{pin.group(1)}{line(version)}{pin.group(3)}"
        planned[where.compose] = "\n".join(lines)
    for path, content in planned.items():
        (root / path).write_text(content, encoding="utf-8")
    check(root, f"v{version}", where)


def notes(root: Path, version: str) -> str:
    """`version`'s changelog section, without its heading."""
    text = _read(root, CHANGELOG)
    match = re.search(rf"(?m)^## {re.escape(version)} — \d{{4}}-\d{{2}}-\d{{2}}$", text)
    if match is None:
        raise VersionError(f"{CHANGELOG} has no dated section for {version}")
    return _section(text, match.group(0)).strip() + "\n"


def _section(text: str, heading: str) -> str:
    """The text under `heading`, up to the next section's."""
    after = text.split(heading + "\n", 1)[1] if heading + "\n" in text else ""
    return re.split(r"(?m)^## ", after, maxsplit=1)[0]


def main(argv: list[str] | None = None) -> int:
    """Run one command; a VersionError is reported and exits 1."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check").add_argument("tag", nargs="?")
    commands.add_parser("set").add_argument("version")
    commands.add_parser("notes").add_argument("version")
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            print(f"every manifest names {check(args.root, args.tag or None)}")
        elif args.command == "set":
            set_version(args.root, args.version, date.today())
        else:
            sys.stdout.write(notes(args.root, args.version))
    except VersionError as error:
        print(f"version: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
