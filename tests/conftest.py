"""Shared pytest fixtures."""

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
