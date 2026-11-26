"""The git identity used for the art commits."""

from pathlib import Path

import git
import pytest

from github_pixel_artworks.identity import Identity, MissingIdentityError, resolve_identity


def test_reads_the_local_config_of_the_folder_the_tool_runs_in(source_checkout: Path) -> None:
    assert resolve_identity() == Identity("Source User", "source@example.com")


def test_falls_back_to_the_global_config(set_global_git_config) -> None:
    set_global_git_config("user.name", "Global User")
    set_global_git_config("user.email", "global@example.com")

    assert resolve_identity() == Identity("Global User", "global@example.com")


def test_the_target_repository_config_wins(source_checkout: Path, tmp_path: Path) -> None:
    target = git.Repo.init(tmp_path / "target")
    with target.config_writer() as cw:
        cw.set_value("user", "email", "target@example.com")

    identity = resolve_identity(Path(str(target.working_tree_dir)))

    assert identity == Identity("Source User", "target@example.com")


def test_git_environment_variables_win(
    source_checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Env User")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "env@example.com")

    assert resolve_identity() == Identity("Env User", "env@example.com")


def test_is_none_when_nothing_is_set() -> None:
    assert resolve_identity() is None


def test_is_none_when_only_the_name_is_set(set_global_git_config) -> None:
    set_global_git_config("user.name", "Global User")

    assert resolve_identity() is None


def test_the_environment_carries_author_and_committer() -> None:
    env = Identity("A U", "a@example.com").env()

    assert env == {
        "GIT_AUTHOR_NAME": "A U",
        "GIT_AUTHOR_EMAIL": "a@example.com",
        "GIT_COMMITTER_NAME": "A U",
        "GIT_COMMITTER_EMAIL": "a@example.com",
    }


def test_the_missing_identity_error_says_how_to_fix_it() -> None:
    message = str(MissingIdentityError())

    assert "git config --global user.email" in message
    assert "git config --global user.name" in message
