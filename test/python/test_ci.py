"""Tests for bin/ci.py, the planner behind .github/workflows/python-docker-app.yml."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "bin" / "ci.py"
spec = importlib.util.spec_from_file_location("ci", SCRIPT)
assert spec and spec.loader
ci = importlib.util.module_from_spec(spec)
sys.modules["ci"] = ci
spec.loader.exec_module(ci)

BACKEND = """
[[ci.suite]]
name = "backend"
python = true
install = 'pip install -e "backend[test]"'
run = "bin/test-backend.sh"
env = { PYTHON = "python" }
coverage = ["backend/coverage.json"]
"""


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """Change into a scratch repository and return a writer for its devtools.toml."""
    monkeypatch.chdir(tmp_path)

    def write(text: str) -> Path:
        path = tmp_path / "devtools.toml"
        path.write_text(text)
        return path

    return write


def git(*args: str) -> str:
    """Run git in the current directory with a fixed identity, and return its output."""
    return subprocess.run(
        [
            "git",
            "-c",
            "user.name=T",
            "-c",
            "user.email=t@example.com",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def commit(path: str, message: str) -> str:
    """Write a file, commit it, and return the commit's SHA."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(message)
    git("add", path)
    git("commit", "-q", "-m", message)
    return git("rev-parse", "HEAD")


class TestLoad:
    def test_defaults(self, repo):
        repo("[ci]\n")
        config = ci.load()
        assert config == {
            "python": "3.14",
            "node": "24",
            "junit": [],
            "coverage_description": "Coverage report",
            "image_tags": "release",
            "revision_arg": "REVISION",
            "provenance": True,
            "images_on_pull_request": True,
            "github_release": True,
            "suites": [],
            "images": [],
        }

    def test_without_a_ci_section(self, repo):
        repo("[fetch]\n")
        assert ci.load()["suites"] == []

    def test_fills_in_a_suite(self, repo):
        repo('[[ci.suite]]\nname = "lint"\nrun = "bin/lint.sh"\n')
        assert ci.load()["suites"] == [
            {
                "name": "lint",
                "python": False,
                "node": False,
                "cache": "",
                "setup": "",
                "install": "",
                "run": "bin/lint.sh",
                "env": {},
                "coverage": [],
                "timeout": 30,
            }
        ]

    def test_keeps_a_suite_as_written(self, repo):
        repo(BACKEND)
        [backend] = ci.load()["suites"]
        assert backend["env"] == {"PYTHON": "python"}
        assert backend["coverage"] == ["backend/coverage.json"]

    def test_fills_in_an_image(self, repo):
        repo(
            '[[ci.image]]\nimage = "ghcr.io/x/app"\n'
            '[[ci.image]]\nimage = "ghcr.io/x/api"\ncontext = "backend/"\n'
            '[[ci.image]]\nimage = "ghcr.io/x/w"\ndockerfile = "w/Dockerfile"\npaths = ["w/"]\n'
        )
        assert ci.load()["images"] == [
            {"image": "ghcr.io/x/app", "context": ".", "dockerfile": "./Dockerfile", "paths": []},
            {
                "image": "ghcr.io/x/api",
                "context": "backend/",
                "dockerfile": "backend/Dockerfile",
                "paths": [],
            },
            {"image": "ghcr.io/x/w", "context": ".", "dockerfile": "w/Dockerfile", "paths": ["w/"]},
        ]

    @pytest.mark.parametrize(
        ("text", "message"),
        [
            ("[ci]\nsuites = []\n", "[ci] has unknown keys: suites"),
            ("[ci]\npython = 3.14\n", "[ci] python must be a str"),
            ('[ci]\nimage_tags = "every"\n', "[ci] image_tags must be one of release, latest"),
            ('[ci]\nrevision_arg = "GIT SHA"\n', "[ci] revision_arg must be a build argument name"),
            ("[ci]\njunit = [1]\n", "[ci] junit must list strings"),
            ("ci = 1\n", "ci in devtools.toml must be a table"),
            ("[ci]\nsuite = [1]\n", "[[ci.suite]] 1 must be a table"),
            ('[[ci.suite]]\nrun = "x"\n', "[[ci.suite]] 1 needs a name"),
            ('[[ci.suite]]\nname = "a b"\nrun = "x"\n', "[[ci.suite]] 1 needs a name"),
            ('[[ci.suite]]\nname = "a"\n', "[[ci.suite]] a needs a run command"),
            (
                '[[ci.suite]]\nname = "a"\nrun = "x"\nruns = "y"\n',
                "[[ci.suite]] 1 has unknown keys: runs",
            ),
            (
                '[[ci.suite]]\nname = "a"\nrun = "x"\ntimeout = true\n',
                "[[ci.suite]] 1 timeout must be a int",
            ),
            (
                '[[ci.suite]]\nname = "a"\nrun = "x"\npython = "yes"\n',
                "[[ci.suite]] 1 python must be a bool",
            ),
            (
                '[[ci.suite]]\nname = "a"\nrun = "x"\nenv = { "A B" = "1" }\n',
                "env must map variable names",
            ),
            (
                '[[ci.suite]]\nname = "a"\nrun = "x"\nenv = { A = 1 }\n',
                "env must map variable names",
            ),
            (
                '[[ci.suite]]\nname = "a"\nrun = "x"\nenv = { A = "1\\n2" }\n',
                "env A must be one line",
            ),
            (
                '[[ci.suite]]\nname = "a"\nrun = "x"\ncoverage = [1]\n',
                "[[ci.suite]] a coverage must list strings",
            ),
            (
                '[[ci.suite]]\nname = "a"\nrun = "x"\n[[ci.suite]]\nname = "a"\nrun = "y"\n',
                "[[ci.suite]] names must be unique: a",
            ),
            ("[ci]\nimage = [1]\n", "[[ci.image]] 1 must be a table"),
            ('[[ci.image]]\ncontext = "."\n', "[[ci.image]] 1 needs an image"),
            ('[[ci.image]]\nimage = "x"\npaths = "a/"\n', "[[ci.image]] 1 paths must be a list"),
            ('[[ci.image]]\nimage = "x"\npaths = [1]\n', "[[ci.image]] 1 paths must list strings"),
        ],
    )
    def test_refuses_a_malformed_section(self, repo, text, message):
        repo(text)
        with pytest.raises(ci.CIError) as e:
            ci.load()
        assert message in str(e.value)

    def test_refuses_a_missing_or_invalid_file(self, repo, tmp_path):
        with pytest.raises(ci.CIError, match="no devtools.toml; run this from the repository root"):
            ci.load()
        repo("[ci\n")
        with pytest.raises(ci.CIError, match="devtools.toml is not valid TOML"):
            ci.load()


class TestChanges:
    @pytest.fixture
    def history(self, repo):
        """A repository with a commit touching backend/, then one touching frontend/."""
        repo("[ci]\n")
        git("init", "-q")
        first = commit("backend/app.py", "backend")
        commit("frontend/app.ts", "frontend")
        return first

    def test_lists_the_files_changed_since_a_commit(self, history):
        assert ci.changed_files(history) == ["frontend/app.ts"]

    @pytest.mark.parametrize("since", [None, "", "0000000000000000000000000000000000000000"])
    def test_no_commit_means_every_image(self, history, since):
        assert ci.changed_files(since) is None

    def test_an_unknown_commit_means_every_image(self, history):
        assert ci.changed_files("deadbeef" * 5) is None

    @pytest.mark.parametrize(
        ("paths", "changed", "built"),
        [
            ([], ["anything"], True),
            (["backend/"], None, True),
            (["backend/"], ["backend/app.py"], True),
            (["backend/"], ["frontend/app.ts"], False),
            (["backend/"], [".github/workflows/ci.yml"], True),
            (["backend/", "shared/"], ["shared/x"], True),
        ],
    )
    def test_an_image_is_built_when_its_paths_changed(self, paths, changed, built):
        assert ci.wanted({"paths": paths}, changed) is built


class TestPlan:
    IMAGES = """
[[ci.image]]
image = "ghcr.io/x/api"
paths = ["backend/"]

[[ci.image]]
image = "ghcr.io/x/web"
paths = ["frontend/"]
"""

    def test_lists_the_suites_and_whether_any_has_coverage(self, repo):
        repo(BACKEND + '[[ci.suite]]\nname = "lint"\nrun = "bin/lint.sh"\n')
        out = ci.plan(ci.load(), "push", None)
        assert [s["name"] for s in json.loads(out["suites"])] == ["backend", "lint"]
        assert out["has_suites"] == "true"
        assert out["coverage"] == "true"

    def test_without_suites(self, repo):
        repo('[[ci.suite]]\nname = "lint"\nrun = "x"\n')
        assert ci.plan(ci.load(), "push", None)["coverage"] == "false"
        repo("[ci]\n")
        out = ci.plan(ci.load(), "push", None)
        assert (out["suites"], out["has_suites"], out["has_images"]) == ("[]", "false", "false")

    def test_builds_only_the_images_a_push_changed(self, repo):
        repo(self.IMAGES)
        git("init", "-q")
        before = commit("backend/a.py", "a")
        commit("frontend/b.ts", "b")
        out = ci.plan(ci.load(), "push", before)
        assert json.loads(out["images"]) == [
            {"image": "ghcr.io/x/web", "context": ".", "dockerfile": "./Dockerfile"}
        ]
        assert out["has_images"] == "true"
        assert out["push"] == "true"

    def test_a_push_that_changes_no_image_builds_none(self, repo):
        repo(self.IMAGES)
        git("init", "-q")
        before = commit("backend/a.py", "a")
        commit("docs/c.md", "c")
        out = ci.plan(ci.load(), "push", before)
        assert (out["images"], out["has_images"]) == ("[]", "false")

    @pytest.mark.parametrize("event", ["workflow_dispatch", "schedule"])
    def test_a_manual_or_scheduled_run_builds_every_image(self, repo, event):
        repo(self.IMAGES)
        git("init", "-q")
        before = commit("docs/c.md", "c")
        commit("docs/d.md", "d")
        assert len(json.loads(ci.plan(ci.load(), event, before)["images"])) == 2

    def test_a_pull_request_builds_without_pushing(self, repo):
        repo('[[ci.image]]\nimage = "ghcr.io/x/app"\n')
        out = ci.plan(ci.load(), "pull_request", None)
        assert (out["has_images"], out["push"]) == ("true", "false")

    def test_a_pull_request_can_build_no_images(self, repo):
        repo('[ci]\nimages_on_pull_request = false\n[[ci.image]]\nimage = "ghcr.io/x/app"\n')
        assert ci.plan(ci.load(), "pull_request", None)["has_images"] == "false"
        assert ci.plan(ci.load(), "push", None)["has_images"] == "true"

    def test_image_settings(self, repo, monkeypatch):
        monkeypatch.setenv("GITHUB_SHA", "abc123")
        repo(
            '[ci]\nimage_tags = "latest"\nrevision_arg = "GIT_SHA"\nprovenance = false\n'
            'github_release = false\njunit = ["a/*.xml", "b/*.xml"]\n'
            'coverage_description = "Report"\npython = "3.13"\nnode = "22"\n'
        )
        out = ci.plan(ci.load(), "push", None)
        assert out["tags"] == "type=sha\ntype=raw,value=latest"
        assert out["build_args"] == "GIT_SHA=abc123"
        assert (out["provenance"], out["github_release"]) == ("false", "false")
        assert out["junit"] == "a/*.xml,b/*.xml"
        assert out["coverage_description"] == "Report"
        assert (out["python"], out["node"]) == ("3.13", "22")

    def test_release_tags_and_no_revision(self, repo):
        repo('[ci]\nrevision_arg = ""\n')
        out = ci.plan(ci.load(), "push", None)
        assert out["tags"].splitlines()[0] == "type=edge"
        assert len(out["tags"].splitlines()) == 5
        assert out["build_args"] == ""


def test_output_lines_delimit_values_that_span_lines():
    text = ci.output_lines({"a": "1", "b": "x\ny"})
    lines = text.splitlines()
    assert lines[0] == "a=1"
    assert lines[1].startswith("b<<EOF_")
    assert lines[2:4] == ["x", "y"]
    assert lines[4] == lines[1].split("<<")[1]


class TestCoverage:
    def test_packs_and_unpacks_at_the_repository_root(self, tmp_path):
        source = tmp_path / "source"
        (source / "backend" / "htmlcov").mkdir(parents=True)
        (source / "backend" / "coverage.json").write_text("{}")
        (source / "backend" / "htmlcov" / "index.html").write_text("<html>")
        entry = {"name": "backend", "coverage": ["backend/coverage.json", "backend/htmlcov"]}
        archive = ci.pack(entry, source)
        assert archive.name == "coverage-backend.tgz"
        downloads = tmp_path / "downloads" / "coverage-backend"
        downloads.mkdir(parents=True)
        archive.rename(downloads / archive.name)
        target = tmp_path / "target"
        target.mkdir()
        assert ci.unpack(tmp_path / "downloads", target) == ["coverage-backend.tgz"]
        assert (target / "backend" / "coverage.json").read_text() == "{}"
        assert (target / "backend" / "htmlcov" / "index.html").read_text() == "<html>"

    def test_leaves_links_out(self, tmp_path):
        source = tmp_path / "source"
        report = source / "coverage" / "shell"
        (report / "run.1").mkdir(parents=True)
        (report / "run.1" / "index.html").write_text("<html>")
        (report / "script.sh").symlink_to(report / "run.1")
        (report / "outside").symlink_to("/etc/passwd")
        archive = ci.pack({"name": "shell", "coverage": ["coverage/shell"]}, source)
        with tarfile.open(archive) as tar:
            names = tar.getnames()
        assert "coverage/shell/run.1/index.html" in names
        assert "coverage/shell/script.sh" not in names
        assert "coverage/shell/outside" not in names
        target = tmp_path / "target"
        target.mkdir()
        assert ci.unpack(source, target) == ["coverage-shell.tgz"]

    def test_refuses_to_pack_a_report_the_suite_did_not_write(self, tmp_path):
        with pytest.raises(ci.CIError, match="suite web left no web/coverage"):
            ci.pack({"name": "web", "coverage": ["web/coverage"]}, tmp_path)

    def test_unpack_refuses_paths_outside_the_repository(self, tmp_path):
        evil = tmp_path / "coverage-evil.tgz"
        payload = tmp_path / "payload"
        payload.write_text("x")
        with tarfile.open(evil, "w:gz") as tar:
            tar.add(payload, arcname="../escaped")
        target = tmp_path / "target"
        target.mkdir()
        with pytest.raises(tarfile.OutsideDestinationError):
            ci.unpack(tmp_path, target)
        assert not (tmp_path / "escaped").exists()


class TestMain:
    def run(self, capsys, *argv):
        status = ci.main(list(argv))
        out, err = capsys.readouterr()
        return status, out, err

    def test_plan(self, repo, capsys):
        repo(BACKEND)
        status, out, err = self.run(capsys, "plan", "--event", "push")
        assert (status, err) == (0, "")
        assert "has_suites=true" in out.splitlines()
        assert any(line.startswith("tags<<EOF_") for line in out.splitlines())

    def test_reports_errors_with_status_1(self, repo, capsys):
        repo('[ci]\nimage_tags = "x"\n')
        status, _, err = self.run(capsys, "plan", "--event", "push")
        assert status == 1
        assert err.startswith("ci: [ci] image_tags must be one of")

    def test_env_appends_the_suites_variables(self, repo, capsys, monkeypatch, tmp_path):
        target = tmp_path / "github_env"
        target.write_text("EXISTING=1\n")
        monkeypatch.setenv("GITHUB_ENV", str(target))
        monkeypatch.setenv("CI_SUITE", json.dumps({"name": "b", "env": {"A": "1", "B": "two"}}))
        assert self.run(capsys, "env")[0] == 0
        assert target.read_text() == "EXISTING=1\nA=1\nB=two\n"

    def test_env_needs_the_workflow_environment(self, repo, capsys, monkeypatch):
        monkeypatch.delenv("GITHUB_ENV", raising=False)
        monkeypatch.setenv("CI_SUITE", "{}")
        assert self.run(capsys, "env") == (
            1,
            "",
            "ci: GITHUB_ENV is not set; this runs inside a workflow\n",
        )
        monkeypatch.setenv("GITHUB_ENV", "x")
        monkeypatch.delenv("CI_SUITE")
        status, _, err = self.run(capsys, "env")
        assert status == 1
        assert "CI_SUITE is not set" in err

    def test_pack_and_unpack(self, repo, capsys, monkeypatch, tmp_path):
        Path("junit").mkdir()
        Path("junit/a.xml").write_text("<a/>")
        monkeypatch.setenv("CI_SUITE", json.dumps({"name": "t", "coverage": ["junit"]}))
        assert self.run(capsys, "pack") == (0, "ci: packed coverage-t.tgz\n", "")
        Path("junit/a.xml").unlink()
        assert self.run(capsys, "unpack", ".") == (0, "ci: unpacked coverage-t.tgz\n", "")
        assert Path("junit/a.xml").read_text() == "<a/>"
        empty = tmp_path / "empty"
        empty.mkdir()
        assert self.run(capsys, "unpack", str(empty)) == (
            0,
            "ci: unpacked no coverage archives\n",
            "",
        )


def test_runs_as_a_script(repo):
    repo(BACKEND)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "plan", "--event", "push"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "has_suites=true" in result.stdout
