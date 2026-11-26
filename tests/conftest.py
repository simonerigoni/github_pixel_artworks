"""Shared pytest fixtures."""

from pathlib import Path

import git
import pytest


@pytest.fixture
def git_repo(tmp_path: Path) -> git.Repo:
    """A throwaway git repository with one commit on ``main`` and a GitHub ``origin``."""
    repo = git.Repo.init(tmp_path / "canvas", initial_branch="main")
    with repo.config_writer() as cw:
        cw.set_value("user", "name", "Test User")
        cw.set_value("user", "email", "test@example.com")
        cw.set_value("commit", "gpgsign", "false")
    root = Path(str(repo.working_tree_dir))
    (root / "source.py").write_text("print('hello')\n", encoding="utf-8")
    (root / ".gitignore").write_text(".env\n", encoding="utf-8")
    repo.index.add(["source.py", ".gitignore"])
    repo.index.commit("initial")
    repo.create_remote("origin", "git@github.com:someone/canvas.git")
    return repo
