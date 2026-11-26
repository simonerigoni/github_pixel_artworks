"""Finding, cloning and pushing the art repository."""

from pathlib import Path

import git
import pytest

from github_pixel_artworks.art_repo import (
    default_branch,
    is_remote_url,
    is_tool_checkout,
    local_checkout_path,
    open_art_repo,
    push_branch,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def ignore(_message: str) -> None:
    pass


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("https://github.com/you/pixel-art", True),
        ("git@github.com:you/pixel-art.git", True),
        ("ssh://git@github.com/you/pixel-art.git", True),
        ("file:///tmp/pixel-art.git", True),
        ("../pixel-art", False),
        ("C:\\Users\\you\\pixel-art", False),
    ],
)
def test_is_remote_url(target: str, expected: bool) -> None:
    assert is_remote_url(target) is expected


class TestLocalCheckoutPath:
    @pytest.mark.parametrize(
        "url",
        [
            "https://github.com/you/pixel-art",
            "https://github.com/you/pixel-art.git/",
            "git@github.com:you/pixel-art.git",
        ],
    )
    def test_a_url_is_cloned_into_a_folder_named_after_the_repo(
        self, tmp_path: Path, url: str
    ) -> None:
        assert local_checkout_path(url, base_dir=tmp_path) == tmp_path / "pixel-art"

    def test_a_path_is_used_as_is(self, tmp_path: Path) -> None:
        assert local_checkout_path(str(tmp_path / "art")) == tmp_path / "art"


class TestOpenArtRepo:
    def test_opens_a_local_repository(self, git_repo: git.Repo) -> None:
        repo = open_art_repo(str(git_repo.working_tree_dir), log=ignore)

        assert repo.working_tree_dir == git_repo.working_tree_dir

    def test_rejects_a_directory_that_is_not_a_repository(self, tmp_path: Path) -> None:
        with pytest.raises(RuntimeError, match="not a git repository"):
            open_art_repo(str(tmp_path), log=ignore)

    def test_clones_a_url_into_the_base_directory(self, tmp_path: Path, empty_remote: str) -> None:
        repo = open_art_repo(empty_remote, base_dir=tmp_path / "work", log=ignore)

        assert Path(str(repo.working_tree_dir)) == tmp_path / "work" / "pixel-art"
        assert repo.remotes.origin.url == empty_remote

    def test_reuses_an_existing_clone_of_the_same_url(
        self, tmp_path: Path, empty_remote: str
    ) -> None:
        first = open_art_repo(empty_remote, base_dir=tmp_path, log=ignore)
        marker = Path(str(first.working_tree_dir)) / "marker.txt"
        marker.write_text("kept", encoding="utf-8")

        second = open_art_repo(empty_remote, base_dir=tmp_path, log=ignore)

        assert second.working_tree_dir == first.working_tree_dir
        assert marker.read_text(encoding="utf-8") == "kept"

    def test_refuses_to_clone_over_an_unrelated_folder(
        self, tmp_path: Path, empty_remote: str
    ) -> None:
        (tmp_path / "pixel-art").mkdir()

        with pytest.raises(RuntimeError, match="already exists"):
            open_art_repo(empty_remote, base_dir=tmp_path, log=ignore)


class TestDefaultBranch:
    def test_is_read_from_the_remote_head_of_a_clone(
        self, tmp_path: Path, filled_remote: str
    ) -> None:
        clone = git.Repo.clone_from(filled_remote, tmp_path / "clone")

        assert default_branch(clone) == "main"

    def test_is_unknown_when_the_remote_head_was_never_fetched(self, git_repo: git.Repo) -> None:
        assert default_branch(git_repo) is None


class TestIsToolCheckout:
    def test_detects_this_project(self) -> None:
        assert is_tool_checkout(PROJECT_ROOT)

    def test_is_false_for_another_folder(self, tmp_path: Path) -> None:
        assert not is_tool_checkout(tmp_path)


class TestPushBranch:
    def test_pushes_the_branch_to_origin(self, tmp_path: Path, git_repo: git.Repo) -> None:
        remote = git.Repo.init(tmp_path / "origin.git", bare=True, initial_branch="main")
        git_repo.remotes.origin.set_url(str(tmp_path / "origin.git"))

        push_branch(git_repo, "main", log=ignore)

        assert remote.heads.main.commit == git_repo.heads.main.commit

    def test_requires_an_origin_remote(self, git_repo: git.Repo) -> None:
        git_repo.delete_remote(git_repo.remotes.origin)

        with pytest.raises(RuntimeError, match="no 'origin' remote"):
            push_branch(git_repo, "main", log=ignore)
