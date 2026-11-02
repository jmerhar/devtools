"""Tests for bin/version.py: one version in every manifest, released from the changelog."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "bin" / "version.py"
spec = importlib.util.spec_from_file_location("version", SCRIPT)
assert spec and spec.loader
version = importlib.util.module_from_spec(spec)
# Registered before it runs, as an import would: its dataclass looks its module up by name.
sys.modules["version"] = version
spec.loader.exec_module(version)

TODAY = date(2026, 11, 2)
CHANGELOG = """# Changelog

## Unreleased

### Added

- Something new.

## 1.1.0 — 2026-10-01

- The previous release.
"""
LOCK = """{
  "name": "web",
  "version": "1.1.0",
  "packages": {
    "": {
      "name": "web",
      "version": "1.1.0",
      "dependencies": {}
    },
    "node_modules/x": {
      "version": "9.9.9"
    }
  }
}
"""
COMPOSE = """services:
  app:
    image: ghcr.io/example/myapp:1
  worker:
    image: "ghcr.io/example/myapp-worker:1"  # the worker
  db:
    image: postgres:17
"""


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """A repository at 1.1.0 with a backend, a frontend with a lockfile, and a compose file."""
    (tmp_path / "devtools.toml").write_text(
        "[version]\n"
        'pyprojects = ["backend/pyproject.toml", "worker/pyproject.toml"]\n'
        'npm = ["frontend"]\n'
        'images = ["ghcr.io/example/myapp", "ghcr.io/example/myapp-worker"]\n'
    )
    for project in ("backend", "worker"):
        (tmp_path / project).mkdir()
        (tmp_path / project / "pyproject.toml").write_text(
            f'[project]\nname = "{project}"\nversion = "1.1.0"\n'
        )
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "package.json").write_text(
        '{\n  "name": "web",\n  "version": "1.1.0"\n}\n'
    )
    (tmp_path / "frontend" / "package-lock.json").write_text(LOCK)
    (tmp_path / "docker-compose.yml").write_text(COMPOSE)
    (tmp_path / "CHANGELOG.md").write_text(CHANGELOG)
    return tmp_path


def replace(path: Path, old: str, new: str) -> None:
    """Replace text in a file, failing if it is not there."""
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new))


def snapshot(root: Path) -> dict[str, str]:
    """Every file in the repository, by path."""
    return {str(p.relative_to(root)): p.read_text() for p in root.rglob("*") if p.is_file()}


class TestCheck:
    def test_reports_the_version_every_manifest_names(self, root):
        assert version.check(root, None) == "1.1.0"

    def test_reads_both_versions_in_a_lockfile(self, root):
        found = version.versions(root, version.layout(root))
        assert found["frontend/package-lock.json"] == "1.1.0"
        assert found["frontend/package-lock.json#1"] == "1.1.0"
        assert "node_modules" not in str(found)

    def test_reports_manifests_that_disagree(self, root):
        replace(
            root / "frontend" / "package-lock.json",
            '"version": "1.1.0",\n      "dep',
            '"version": "1.0.0",\n      "dep',
        )
        with pytest.raises(version.VersionError, match="different versions") as e:
            version.check(root, None)
        assert "frontend/package-lock.json#1: 1.0.0" in str(e.value)

    def test_npm_spells_a_development_version_as_semver(self, root):
        for project in ("backend", "worker"):
            replace(root / project / "pyproject.toml", "1.1.0", "1.2.0.dev0")
        replace(root / "frontend" / "package.json", "1.1.0", "1.2.0-dev.0")
        lock = root / "frontend" / "package-lock.json"
        lock.write_text(lock.read_text().replace('"version": "1.1.0"', '"version": "1.2.0-dev.0"'))
        assert version.check(root, None) == "1.2.0.dev0"
        version.set_version(root, "1.2.0", TODAY)
        assert lock.read_text().count('"version": "1.2.0"') == 2

    def test_a_development_version_must_match_across_spellings(self, root):
        for project in ("backend", "worker"):
            replace(root / project / "pyproject.toml", "1.1.0", "1.2.0.dev0")
        replace(root / "frontend" / "package.json", "1.1.0", "1.2.0-dev.1")
        (root / "frontend" / "package-lock.json").unlink()
        with pytest.raises(version.VersionError, match="frontend/package.json: 1.2.0.dev1"):
            version.check(root, None)

    def test_reads_a_lockfile_whose_root_package_has_no_name(self, root):
        lock = root / "frontend" / "package-lock.json"
        lock.write_text(lock.read_text().replace('      "name": "web",\n', ""))
        assert version.check(root, None) == "1.1.0"

    def test_a_lockfile_is_optional(self, root):
        (root / "frontend" / "package-lock.json").unlink()
        assert version.check(root, None) == "1.1.0"

    def test_reports_a_missing_manifest(self, root):
        (root / "worker" / "pyproject.toml").unlink()
        with pytest.raises(version.VersionError, match="worker/pyproject.toml is missing"):
            version.check(root, None)

    def test_reports_a_manifest_without_a_version(self, root):
        (root / "worker" / "pyproject.toml").write_text('[project]\nname = "worker"\n')
        with pytest.raises(version.VersionError, match="names no version where one is expected"):
            version.check(root, None)

    def test_rejects_a_version_that_is_not_a_release_or_development_one(self, root):
        for path in ("backend", "worker"):
            replace(root / path / "pyproject.toml", "1.1.0", "1.1")
        (root / "devtools.toml").write_text(
            '[version]\npyprojects = ["backend/pyproject.toml", "worker/pyproject.toml"]\n'
        )
        with pytest.raises(version.VersionError, match="1.1 is neither a release"):
            version.check(root, None)

    def test_a_tag_must_match_the_manifests(self, root):
        with pytest.raises(version.VersionError, match="the tag is v1.2.0, but the manifests"):
            version.check(root, "v1.2.0")

    def test_a_tag_needs_its_dated_changelog_section(self, root):
        with pytest.raises(version.VersionError, match="no dated section for 1.1.0"):
            replace(root / "CHANGELOG.md", "## 1.1.0 — 2026-10-01", "## 1.1.0")
            version.check(root, "v1.1.0")

    def test_a_tag_with_its_section_passes(self, root):
        assert version.check(root, "v1.1.0") == "1.1.0"


class TestCompose:
    def test_requires_each_image_on_the_release_line(self, root):
        replace(root / "docker-compose.yml", "myapp-worker:1", "myapp-worker:2")
        with pytest.raises(version.VersionError) as e:
            version.check(root, None)
        assert str(e.value) == (
            "docker-compose.yml pins ghcr.io/example/myapp-worker:2, not 1 as 1.1.0 is"
        )

    def test_rejects_an_image_without_a_plain_tag(self, root):
        replace(root / "docker-compose.yml", "myapp:1", "myapp@sha256:abc")
        with pytest.raises(version.VersionError, match="line 3 names an image without a plain tag"):
            version.check(root, None)

    def test_reports_each_listed_image_the_compose_file_does_not_name(self, root):
        (root / "docker-compose.yml").write_text(
            "services:\n  app:\n    image: ghcr.io/example/myapp:1\n  db:\n    image: postgres:17\n"
        )
        with pytest.raises(version.VersionError) as e:
            version.check(root, None)
        assert str(e.value) == "docker-compose.yml does not name ghcr.io/example/myapp-worker"

    def test_rejects_a_tag_pinned_to_a_digest(self, root):
        replace(root / "docker-compose.yml", "myapp:1\n", "myapp:1@sha256:abc\n")
        with pytest.raises(version.VersionError, match="line 3 names an image without a plain tag"):
            version.check(root, None)

    def test_leaves_an_image_whose_name_only_starts_with_a_listed_one(self, root):
        (root / "devtools.toml").write_text(
            '[version]\npyprojects = ["backend/pyproject.toml"]\n'
            'images = ["ghcr.io/example/myapp"]\n'
        )
        (root / "docker-compose.yml").write_text(
            "services:\n  app:\n    image: ghcr.io/example/myapp:1\n"
            "  other:\n    image: ghcr.io/example/myapp-other@sha256:abc\n"
        )
        assert version.check(root, None) == "1.1.0"
        version.set_version(root, "2.0.0", TODAY)
        assert "myapp-other@sha256:abc" in (root / "docker-compose.yml").read_text()

    def test_rewrites_the_pin_line_past_other_line_separators(self, root):
        replace(
            root / "docker-compose.yml",
            "services:\n",
            "# caf\u00e9\u2028note\u000cpage\nservices:\n",
        )
        version.set_version(root, "2.0.0", TODAY)
        compose = (root / "docker-compose.yml").read_text()
        assert "    image: ghcr.io/example/myapp:2\n" in compose
        assert "\u2028note" in compose
        assert compose.count("myapp:2") == 1

    def test_reads_another_compose_file(self, root):
        (root / "devtools.toml").write_text(
            '[version]\npyprojects = ["backend/pyproject.toml"]\n'
            'images = ["ghcr.io/example/myapp"]\ncompose = "deploy/compose.yml"\n'
        )
        (root / "deploy").mkdir()
        (root / "deploy" / "compose.yml").write_text(
            "services:\n  app:\n    image: ghcr.io/example/myapp:2\n"
        )
        with pytest.raises(version.VersionError, match="deploy/compose.yml pins"):
            version.check(root, None)

    def test_without_images_the_compose_file_is_not_read(self, root):
        (root / "devtools.toml").write_text('[version]\npyprojects = ["backend/pyproject.toml"]\n')
        (root / "docker-compose.yml").unlink()
        assert version.check(root, None) == "1.1.0"

    @pytest.mark.parametrize(
        ("release", "expected"),
        [
            ("1.2.3", "1"),
            ("2.0.0", "2"),
            ("0.3.1", "0.3"),
            ("0.4.0.dev0", "0.4"),
            ("3.0.0.dev2", "3"),
        ],
    )
    def test_the_line_is_the_major_or_before_1_0_the_minor(self, release, expected):
        assert version.line(release) == expected


class TestSet:
    def test_writes_every_manifest_the_compose_file_and_the_changelog(self, root):
        version.set_version(root, "2.0.0", TODAY)
        assert version.check(root, "v2.0.0") == "2.0.0"
        assert 'version = "2.0.0"' in (root / "worker" / "pyproject.toml").read_text()
        lock = (root / "frontend" / "package-lock.json").read_text()
        assert lock.count('"version": "2.0.0"') == 2
        assert '"version": "9.9.9"' in lock
        compose = (root / "docker-compose.yml").read_text()
        assert "myapp:2\n" in compose
        assert '"ghcr.io/example/myapp-worker:2"  # the worker' in compose
        assert "postgres:17" in compose
        assert "## Unreleased" not in (root / "CHANGELOG.md").read_text()
        assert version.notes(root, "2.0.0") == "### Added\n\n- Something new.\n"

    def test_a_release_follows_its_development_version(self, root):
        for path in ("backend", "worker"):
            replace(root / path / "pyproject.toml", "1.1.0", "1.2.0.dev0")
        (root / "devtools.toml").write_text(
            '[version]\npyprojects = ["backend/pyproject.toml", "worker/pyproject.toml"]\n'
        )
        version.set_version(root, "1.2.0", TODAY)
        assert version.check(root, None) == "1.2.0"

    @pytest.mark.parametrize("release", ["1.1.0", "1.0.9"])
    def test_refuses_a_version_that_is_not_after_the_current_one(self, root, release):
        with pytest.raises(version.VersionError, match=f"{release} is not after 1.1.0"):
            version.set_version(root, release, TODAY)

    def test_refuses_a_version_that_is_not_a_release(self, root):
        with pytest.raises(version.VersionError, match="1.2 is not a version like 1.2.3"):
            version.set_version(root, "1.2", TODAY)

    @pytest.mark.parametrize(
        ("changelog", "message"),
        [
            ("# Changelog\n\n## 1.1.0 — 2026-10-01\n", "has no '## Unreleased' section"),
            ("## Unreleased\n\n- a\n\n## Unreleased\n\n- b\n", "has more than one"),
            ("## Unreleased\n\n### Added\n\n## 1.1.0 — 2026-10-01\n", "section is empty"),
            ("## Unreleased\n\n- a\n\n## 1.2.0 — 2026-10-02\n", "already has a section for 1.2.0"),
        ],
    )
    def test_refuses_a_changelog_it_cannot_release(self, root, changelog, message):
        (root / "CHANGELOG.md").write_text(changelog)
        with pytest.raises(version.VersionError, match=message):
            version.set_version(root, "1.2.0", TODAY)

    def test_changes_nothing_when_it_refuses(self, root):
        replace(root / "docker-compose.yml", "myapp:1", "myapp@sha256:abc")
        before = snapshot(root)
        with pytest.raises(version.VersionError):
            version.set_version(root, "1.2.0", TODAY)
        assert snapshot(root) == before


class TestLayout:
    def test_needs_at_least_one_manifest(self, root):
        (root / "devtools.toml").write_text('[version]\nimages = ["x"]\n')
        with pytest.raises(version.VersionError, match="lists no manifests"):
            version.layout(root)

    def test_reports_a_setting_of_the_wrong_shape(self, root):
        (root / "devtools.toml").write_text('[version]\npyprojects = "backend/pyproject.toml"\n')
        with pytest.raises(version.VersionError, match="version.pyprojects must be a list"):
            version.layout(root)

    def test_the_compose_setting_is_one_file(self, root):
        (root / "devtools.toml").write_text(
            '[version]\npyprojects = ["backend/pyproject.toml"]\ncompose = ["a.yml", "b.yml"]\n'
        )
        with pytest.raises(version.VersionError, match="version.compose must be one file"):
            version.layout(root)

    def test_reports_a_missing_devtools_toml(self, tmp_path):
        with pytest.raises(version.VersionError, match="devtools.toml; run this from"):
            version.layout(tmp_path)


class TestMain:
    def run(self, capsys, root, *argv):
        status = version.main(["--root", str(root), *argv])
        out, err = capsys.readouterr()
        return status, out, err

    def test_check(self, capsys, root):
        assert self.run(capsys, root, "check") == (0, "every manifest names 1.1.0\n", "")

    def test_an_empty_tag_is_no_tag(self, capsys, root):
        assert self.run(capsys, root, "check", "")[0] == 0

    def test_set_then_notes(self, capsys, root):
        assert self.run(capsys, root, "set", "1.2.0") == (0, "", "")
        assert self.run(capsys, root, "notes", "1.2.0") == (
            0,
            "### Added\n\n- Something new.\n",
            "",
        )

    def test_reports_errors_with_status_1(self, capsys, root):
        status, out, err = self.run(capsys, root, "notes", "9.9.9")
        assert (status, out) == (1, "")
        assert err == "version: CHANGELOG.md has no dated section for 9.9.9\n"

    def test_defaults_to_the_current_directory(self, capsys, root, monkeypatch):
        monkeypatch.chdir(root)
        assert version.main(["check"]) == 0
