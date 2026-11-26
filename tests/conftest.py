"""Shared pytest fixtures."""

import subprocess
import urllib.error
from pathlib import Path

import git
import pytest

TEST_EMAIL = "test@example.com"


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail every HTTP request, so no test depends on the network or GitHub."""

    def no_network(*_args: object, **_kwargs: object) -> None:
        raise urllib.error.URLError("network disabled in tests")

    monkeypatch.setattr("urllib.request.urlopen", no_network)


@pytest.fixture(autouse=True)
def global_git_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """No git settings and no ``gh``, so no test sees the real user's settings.

    The global config is an empty file, system config is off, and tests run in an
    empty directory outside any repository, so this clone's own settings stay out.
    """
    path = tmp_path / "gitconfig"
    path.write_text("", encoding="utf-8")
    workdir = tmp_path / "cwd"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    for variable in ("NAME", "EMAIL"):
        for role in ("AUTHOR", "COMMITTER"):
            monkeypatch.delenv(f"GIT_{role}_{variable}", raising=False)
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(path))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setattr("github_pixel_artworks.github.GH_COMMAND", "gh-not-installed-in-tests")
    return path


@pytest.fixture(autouse=True)
def clone_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Project root used for URL-target clones during a test, not the real checkout."""
    path = tmp_path / "tool-root"
    path.mkdir()
    monkeypatch.setattr("github_pixel_artworks.art_repo.tool_project_root", lambda: path)
    return path


@pytest.fixture
def set_global_git_config(global_git_config: Path):
    """Set a key in the isolated global git config."""

    def set_value(key: str, value: str) -> None:
        subprocess.run(["git", "config", "--file", str(global_git_config), key, value], check=True)

    return set_value


@pytest.fixture
def fake_gh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Install a fake ``gh`` that runs the given shell snippet."""

    def install(script: str) -> None:
        path = tmp_path / "bin" / "gh"
        path.parent.mkdir(exist_ok=True)
        path.write_text(f"#!/bin/sh\n{script}\n", encoding="utf-8")
        path.chmod(0o755)
        monkeypatch.setattr("github_pixel_artworks.github.GH_COMMAND", str(path))

    return install


@pytest.fixture
def git_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """A commit identity for repositories without one, such as fresh clones."""
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Test User")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", TEST_EMAIL)


@pytest.fixture
def git_repo(tmp_path: Path) -> git.Repo:
    """A throwaway git repository with one commit on ``main`` and a GitHub ``origin``."""
    repo = git.Repo.init(tmp_path / "canvas", initial_branch="main")
    with repo.config_writer() as cw:
        cw.set_value("user", "name", "Test User")
        cw.set_value("user", "email", TEST_EMAIL)
        cw.set_value("commit", "gpgsign", "false")
    root = Path(str(repo.working_tree_dir))
    (root / "source.py").write_text("print('hello')\n", encoding="utf-8")
    (root / ".gitignore").write_text(".env\n", encoding="utf-8")
    repo.index.add(["source.py", ".gitignore"])
    repo.index.commit("initial")
    repo.create_remote("origin", "git@github.com:someone/canvas.git")
    return repo


@pytest.fixture
def source_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A checkout the tool runs from, whose identity is only in its local git config."""
    repo = git.Repo.init(tmp_path / "projects" / "tool", initial_branch="main")
    with repo.config_writer() as cw:
        cw.set_value("user", "name", "Source User")
        cw.set_value("user", "email", "source@example.com")
    root = Path(str(repo.working_tree_dir))
    (root / "sub").mkdir()
    monkeypatch.chdir(root / "sub")
    return root


@pytest.fixture
def empty_remote(tmp_path: Path) -> str:
    """The ``file://`` URL of an empty bare repository, like a new repo on GitHub."""
    path = tmp_path / "remote" / "pixel-art.git"
    git.Repo.init(path, bare=True, initial_branch="main")
    return path.as_uri()


@pytest.fixture
def filled_remote(tmp_path: Path, git_repo: git.Repo) -> str:
    """The ``file://`` URL of a bare repository whose ``main`` holds ``git_repo``'s commit."""
    path = tmp_path / "remote" / "canvas.git"
    git.Repo.init(path, bare=True, initial_branch="main")
    git_repo.git.push(path.as_uri(), "main")
    return path.as_uri()
