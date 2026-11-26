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
    """An empty global git config, and no ``gh``, so no test sees the real user's settings."""
    path = tmp_path / "gitconfig"
    path.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(path))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setattr("github_pixel_artworks.github.GH_COMMAND", "gh-not-installed-in-tests")
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
