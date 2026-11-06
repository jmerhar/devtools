"""Tests for bin/ci.py, the planner behind .github/workflows/python-docker-app.yml."""

from __future__ import annotations

import importlib.util
import json
import os
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

LINT = '[[ci.suite]]\nname = "lint"\nrun = "bin/lint.sh"\n'
BACKEND = """
[[ci.suite]]
name = "backend"
python = true
install = 'pip install -e "backend[test]"'
run = "bin/test-backend.sh"
env = { PYTHON = "python" }
coverage = ["backend/coverage.json"]
"""
MAIN = {"ref": "refs/heads/main", "default_branch": "main"}


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
    identity = ["-c", "user.name=T", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false"]
    return subprocess.run(
        ["git", *identity, *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def commit(path: str, content: str) -> str:
    """Write a file, commit it, and return the commit's SHA."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(content)
    git("add", "-A")
    git("commit", "-q", "-m", content)
    return git("rev-parse", "HEAD")


class TestLoad:
    def test_defaults(self, repo):
        repo(LINT)
        config = ci.load()
        assert {k: v for k, v in config.items() if k != "suites"} == {
            "python": "3.14",
            "node": "24",
            "junit": [],
            "coverage_description": "Coverage report",
            "image_tags": "release",
            "revision_arg": "REVISION",
            "provenance": True,
            "images_on_pull_request": True,
            "github_release": True,
            "images": [],
        }
        assert config["suites"] == [
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

    def test_accepts_urls_without_a_password(self, repo):
        repo(
            '[[ci.suite]]\nname = "a"\nrun = "curl https://example.com/a:b && echo x@y"\n'
            'env = { DB = "postgresql://user@localhost/db" }\n'
        )
        assert ci.load()["suites"][0]["env"]["DB"] == "postgresql://user@localhost/db"

    def test_keeps_a_suite_as_written(self, repo):
        repo(BACKEND)
        [backend] = ci.load()["suites"]
        assert backend["env"] == {"PYTHON": "python"}
        assert backend["coverage"] == ["backend/coverage.json"]

    def test_fills_in_an_image(self, repo):
        repo(
            '[[ci.image]]\nimage = "ghcr.io/x/app"\n'
            '[[ci.image]]\nimage = "ghcr.io/x/api"\ncontext = "backend/"\n'
            '[[ci.image]]\nimage = "ghcr.io/x/w"\ndockerfile = "w.Dockerfile"\npaths = ["w/"]\n'
        )
        assert ci.load()["images"] == [
            {"image": "ghcr.io/x/app", "context": ".", "dockerfile": "./Dockerfile", "paths": []},
            {
                "image": "ghcr.io/x/api",
                "context": "backend/",
                "dockerfile": "backend/Dockerfile",
                "paths": [],
            },
            {
                "image": "ghcr.io/x/w",
                "context": ".",
                "dockerfile": "w.Dockerfile",
                "paths": ["w/", "w.Dockerfile"],
            },
        ]

    @pytest.mark.parametrize(
        ("text", "message"),
        [
            ("[fetch]\n", "devtools.toml has no [ci] section"),
            ("[CI]\n" + LINT.replace("ci.", "CI."), "devtools.toml has no [ci] section"),
            ("[ci]\n", "declares no [[ci.suite]] and no [[ci.image]]"),
            ("[ci]\nsuites = []\n", "[ci] has unknown keys: suites"),
            ("[ci]\npython = 3.14\n", "[ci] python must be a str"),
            ('[ci]\nimage_tags = "every"\n', "[ci] image_tags must be one of release, latest"),
            ('[ci]\nrevision_arg = "GIT SHA"\n', "[ci] revision_arg must be a build argument name"),
            ("[ci]\njunit = [1]\n", "[ci] junit must list strings"),
            ("ci = 1\n", "ci in devtools.toml must be a table"),
            ("[ci]\nsuite = [1]\n", "[[ci.suite]] 1 must be a table"),
            ('[[ci.suite]]\nrun = "x"\n', "[[ci.suite]] 1 needs a name"),
            ('[[ci.suite]]\nname = "a b"\nrun = "x"\n', "[[ci.suite]] 1 needs a name"),
            ('[[ci.suite]]\nname = ".a"\nrun = "x"\n', "[[ci.suite]] 1 needs a name"),
            ('[[ci.suite]]\nname = "-a"\nrun = "x"\n', "[[ci.suite]] 1 needs a name"),
            ('[[ci.suite]]\nname = "a"\n', "[[ci.suite]] a needs a run command"),
            ('[[ci.suite]]\nname = "a"\nrun = "x"\nruns = "y"\n', "1 has unknown keys: runs"),
            ('[[ci.suite]]\nname = "a"\nrun = "x"\ntimeout = true\n', "timeout must be a int"),
            ('[[ci.suite]]\nname = "a"\nrun = "x"\ntimeout = 0\n', "timeout must be a positive"),
            ('[[ci.suite]]\nname = "a"\nrun = "x"\npython = "yes"\n', "python must be a bool"),
            ('[[ci.suite]]\nname = "a"\nrun = "x"\nenv = { "A B" = "1" }\n', "map variable names"),
            ('[[ci.suite]]\nname = "a"\nrun = "x"\nenv = { A = 1 }\n', "map variable names"),
            ('[[ci.suite]]\nname = "a"\nrun = "x"\nenv = { A = "1\\n2" }\n', "env A must be one"),
            ('[[ci.suite]]\nname = "a"\nrun = "x"\nenv = { A = "1\\r2" }\n', "env A must be one"),
            ('[[ci.suite]]\nname = "a"\nrun = "x"\nenv = { NODE_OPTIONS = "x" }\n', "cannot set"),
            ('[[ci.suite]]\nname = "a"\nrun = "x"\nenv = { GITHUB_SHA = "x" }\n', "cannot set"),
            ('[[ci.suite]]\nname = "a"\nrun = "x"\nenv = { RUNNER_OS = "x" }\n', "cannot set"),
            ('[[ci.suite]]\nname = "a"\nrun = "x"\ncoverage = [1]\n', "coverage must list strings"),
            ('[[ci.suite]]\nname = "a"\nrun = "x"\ncoverage = ["/etc/x"]\n', "inside the repo"),
            ('[[ci.suite]]\nname = "a"\nrun = "x"\ncoverage = ["a/../.."]\n', "inside the repo"),
            (LINT + LINT, "[[ci.suite]] names must be unique: lint"),
            (
                '[[ci.suite]]\nname = "a"\nrun = "x"\nenv = { DB = "postgresql://u:p@h/d" }\n',
                "[[ci.suite]] a env DB holds a URL with a password",
            ),
            (
                '[[ci.suite]]\nname = "a"\nrun = "curl https://u:secret@example.com/x"\n',
                "[[ci.suite]] a run holds a URL with a password",
            ),
            (
                '[[ci.suite]]\nname = "a"\nrun = "x"\nsetup = "git clone https://t:x@h/r"\n',
                "[[ci.suite]] a setup holds a URL with a password",
            ),
            ("[ci]\nimage = [1]\n", "[[ci.image]] 1 must be a table"),
            ('[[ci.image]]\ncontext = "."\n', "[[ci.image]] 1 needs an image"),
            ('[[ci.image]]\nimage = "x"\npaths = "a/"\n', "[[ci.image]] 1 paths must be a list"),
            ('[[ci.image]]\nimage = "x"\npaths = [1]\n', "[[ci.image]] 1 paths must list strings"),
            ('[[ci.image]]\nimage = "x"\npaths = ["../a"]\n', "paths must name paths inside"),
        ],
    )
    def test_refuses_a_malformed_section(self, repo, text, message):
        repo(text)
        with pytest.raises(ci.CIError) as e:
            ci.load()
        assert message in str(e.value)

    def test_a_coverage_gate_needs_a_suite_that_keeps_reports(self, repo):
        repo(LINT)
        Path("coverage.toml").write_text("[suites.backend]\n")
        with pytest.raises(ci.CIError, match="coverage.toml sets coverage gates, but no"):
            ci.load()
        repo(LINT + BACKEND)
        assert ci.load()["suites"][1]["coverage"] == ["backend/coverage.json"]

    def test_refuses_a_missing_or_invalid_file(self, repo):
        with pytest.raises(ci.CIError, match="no devtools.toml; run this from the repository root"):
            ci.load()
        repo("[ci\n")
        with pytest.raises(ci.CIError, match="devtools.toml is not valid TOML"):
            ci.load()


class TestChanges:
    @pytest.fixture
    def history(self, repo):
        """A repository with a commit touching backend/, then one touching frontend/."""
        repo(LINT)
        git("init", "-q")
        first = commit("backend/app.py", "backend")
        commit("frontend/app.ts", "frontend")
        return first

    def test_lists_the_files_changed_since_a_commit(self, history):
        assert ci.changed_files(history) == ["frontend/app.ts"]

    @pytest.mark.parametrize("since", [None, "", "0000000000000000000000000000000000000000"])
    def test_no_commit_means_every_image_without_asking_git(self, history, since, monkeypatch):
        monkeypatch.setattr(ci.subprocess, "run", lambda *_a, **_k: pytest.fail("git was run"))
        assert ci.changed_files(since) is None

    def test_an_unknown_commit_means_every_image(self, history):
        assert ci.changed_files("deadbeef" * 5) is None

    def test_a_force_push_counts_everything_the_old_head_lacked(self, repo):
        repo(LINT)
        git("init", "-q", "-b", "main")
        commit("docs/a.md", "base")
        git("checkout", "-q", "-b", "old")
        old = commit("frontend/x.ts", "dropped")
        git("checkout", "-q", "main")
        commit("backend/y.py", "replacement")
        assert sorted(ci.changed_files(old)) == ["backend/y.py", "frontend/x.ts"]

    def test_a_rename_counts_both_sides(self, repo):
        repo(LINT)
        git("init", "-q")
        before = commit("backend/util.py", "x" * 200)
        Path("shared").mkdir()
        git("mv", "backend/util.py", "shared/util.py")
        git("commit", "-q", "-m", "move")
        assert sorted(ci.changed_files(before)) == ["backend/util.py", "shared/util.py"]

    def test_names_come_unquoted(self, repo):
        repo(LINT)
        git("init", "-q")
        before = commit("docs/a.md", "a")
        commit("frontend/locales/français.json", "b")
        assert ci.changed_files(before) == ["frontend/locales/français.json"]

    @pytest.mark.parametrize(
        ("paths", "changed", "built"),
        [
            ([], ["anything"], True),
            (["backend/"], None, True),
            (["backend/"], ["backend/app.py"], True),
            (["backend/"], ["frontend/app.ts"], False),
            (["backend"], ["backend-legacy/app.py"], False),
            (["./backend"], ["backend/app.py"], True),
            (["Dockerfile.api"], ["Dockerfile.api"], True),
            (["backend/"], [".github/workflows/ci.yml"], True),
            (["backend/"], ["devtools.toml"], True),
            (["backend/"], ["docs/devtools.toml"], False),
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
        repo(BACKEND + LINT)
        out = ci.plan(ci.load(), "push", None, **MAIN)
        assert [s["name"] for s in json.loads(out["suites"])] == ["backend", "lint"]
        assert (out["has_suites"], out["coverage"]) == ("true", "true")

    def test_without_coverage_or_suites(self, repo):
        repo(LINT)
        assert ci.plan(ci.load(), "push", None, **MAIN)["coverage"] == "false"
        repo('[[ci.image]]\nimage = "ghcr.io/x/app"\n')
        out = ci.plan(ci.load(), "push", None, **MAIN)
        assert (out["suites"], out["has_suites"], out["has_images"]) == ("[]", "false", "true")

    def test_builds_only_the_images_a_push_changed(self, repo):
        repo(self.IMAGES)
        git("init", "-q")
        before = commit("backend/a.py", "a")
        commit("frontend/b.ts", "b")
        out = ci.plan(ci.load(), "push", before, **MAIN)
        assert json.loads(out["images"]) == [
            {"image": "ghcr.io/x/web", "context": ".", "dockerfile": "./Dockerfile"}
        ]
        assert (out["has_images"], out["push"]) == ("true", "true")

    def test_a_push_that_changes_no_image_builds_none(self, repo):
        repo(self.IMAGES)
        git("init", "-q")
        before = commit("backend/a.py", "a")
        commit("docs/c.md", "c")
        out = ci.plan(ci.load(), "push", before, **MAIN)
        assert (out["images"], out["has_images"]) == ("[]", "false")

    @pytest.mark.parametrize(
        ("event", "ref"),
        [
            ("workflow_dispatch", "refs/heads/main"),
            ("schedule", "refs/heads/main"),
            ("push", "refs/tags/v1.2.0"),
        ],
    )
    def test_a_tag_or_a_manual_or_scheduled_run_builds_every_image(self, repo, event, ref):
        repo(self.IMAGES)
        git("init", "-q")
        before = commit("docs/c.md", "c")
        commit("docs/d.md", "d")
        out = ci.plan(ci.load(), event, before, ref, "main")
        assert len(json.loads(out["images"])) == 2

    @pytest.mark.parametrize(
        ("event", "ref", "push"),
        [
            ("push", "refs/heads/main", "true"),
            ("push", "refs/tags/v1.2.0", "true"),
            ("workflow_dispatch", "refs/heads/main", "true"),
            ("push", "refs/heads/feature", "false"),
            ("workflow_dispatch", "refs/heads/feature", "false"),
            ("workflow_dispatch", "refs/tags/v1.2.0", "true"),
            ("pull_request", "refs/pull/4/merge", "false"),
            ("pull_request_target", "refs/heads/main", "false"),
        ],
    )
    def test_images_are_pushed_only_from_the_default_branch_and_tags(self, repo, event, ref, push):
        repo('[[ci.image]]\nimage = "ghcr.io/x/app"\n')
        out = ci.plan(ci.load(), event, None, ref, "main")
        assert (out["has_images"], out["push"]) == ("true", push)

    def test_without_a_default_branch_nothing_is_pushed_but_tags(self, repo):
        repo('[[ci.image]]\nimage = "ghcr.io/x/app"\n')
        assert ci.plan(ci.load(), "push", None, "refs/heads/main", "")["push"] == "false"
        assert ci.plan(ci.load(), "push", None, "refs/tags/v1.0.0", "")["push"] == "true"

    def test_a_pull_request_can_build_no_images(self, repo):
        repo('[ci]\nimages_on_pull_request = false\n[[ci.image]]\nimage = "ghcr.io/x/app"\n')
        out = ci.plan(ci.load(), "pull_request", None, "refs/pull/1/merge", "main")
        assert out["has_images"] == "false"
        assert ci.plan(ci.load(), "push", None, **MAIN)["has_images"] == "true"

    def test_image_settings(self, repo, monkeypatch):
        monkeypatch.setenv("GITHUB_SHA", "abc123")
        repo(
            '[ci]\nimage_tags = "latest"\nrevision_arg = "GIT_SHA"\nprovenance = false\n'
            'github_release = false\njunit = ["a/*.xml", "b/*.xml"]\n'
            'coverage_description = "Report"\npython = "3.13"\nnode = "22"\n' + LINT
        )
        out = ci.plan(ci.load(), "push", None, **MAIN)
        assert out["tags"] == "type=sha\ntype=raw,value=latest"
        assert out["build_args"] == "GIT_SHA=abc123"
        assert (out["provenance"], out["github_release"]) == ("false", "false")
        assert out["junit"] == "a/*.xml,b/*.xml"
        assert out["coverage_description"] == "Report"
        assert (out["python"], out["node"]) == ("3.13", "22")

    def test_release_tags_and_no_revision(self, repo):
        repo('[ci]\nrevision_arg = ""\n' + LINT)
        out = ci.plan(ci.load(), "push", None, **MAIN)
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

    def test_leaves_symbolic_links_out_and_keeps_hard_links(self, tmp_path):
        source = tmp_path / "source"
        report = source / "coverage" / "shell"
        (report / "run.1").mkdir(parents=True)
        (report / "run.1" / "index.html").write_text("<html>")
        (report / "script.sh").symlink_to(report / "run.1")
        (report / "outside").symlink_to("/etc/passwd")
        os.link(report / "run.1" / "index.html", report / "copy.html")
        archive = ci.pack({"name": "shell", "coverage": ["coverage/shell"]}, source)
        with tarfile.open(archive) as tar:
            names = tar.getnames()
        assert "coverage/shell/run.1/index.html" in names
        assert "coverage/shell/copy.html" in names
        assert "coverage/shell/script.sh" not in names
        assert "coverage/shell/outside" not in names
        target = tmp_path / "target"
        target.mkdir()
        assert ci.unpack(source, target) == ["coverage-shell.tgz"]
        assert (target / "coverage" / "shell" / "copy.html").read_text() == "<html>"

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

    def test_unpack_refuses_a_link_to_an_absolute_path(self, tmp_path):
        evil = tmp_path / "coverage-link.tgz"
        link = tarfile.TarInfo("coverage/hosts")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/hosts"
        with tarfile.open(evil, "w:gz") as tar:
            tar.addfile(link)
        target = tmp_path / "target"
        target.mkdir()
        with pytest.raises(tarfile.AbsoluteLinkError):
            ci.unpack(tmp_path, target)


class TestMain:
    def run(self, capsys, *argv):
        status = ci.main(list(argv))
        out, err = capsys.readouterr()
        return status, out, err

    def test_plan(self, repo, capsys):
        repo(BACKEND + '[[ci.image]]\nimage = "ghcr.io/x/app"\n')
        status, out, err = self.run(
            capsys, "plan", "--event", "push", "--ref", "refs/heads/dev", "--default-branch", "dev"
        )
        assert (status, err) == (0, "")
        assert "has_suites=true" in out.splitlines()
        assert "push=true" in out.splitlines()
        assert any(line.startswith("tags<<EOF_") for line in out.splitlines())

    def test_reports_errors_with_status_1(self, repo, capsys):
        repo('[ci]\nimage_tags = "x"\n')
        status, _, err = self.run(
            capsys,
            "plan",
            "--event",
            "push",
            "--ref",
            "refs/heads/main",
            "--default-branch",
            "main",
        )
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
    command = [sys.executable, str(SCRIPT), "plan", "--event", "push"]
    command += ["--ref", "refs/heads/main", "--default-branch", "main"]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert "has_suites=true" in result.stdout
