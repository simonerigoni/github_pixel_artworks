"""Finding, cloning and pushing the art repository."""

import os
import stat
from pathlib import Path

import git
import pytest
from git.exc import GitCommandError

from github_pixel_artworks.art_repo import (
    clone_url_target,
    default_branch,
    find_tool_project_root,
    has_unpushed_commits,
    is_remote_url,
    is_tool_checkout,
    local_checkout_path,
    open_art_repo,
    push_branch,
    remove_dir_if_empty,
    remove_tree,
    target_clone_parent,
)
from github_pixel_artworks.config import TARGET_CLONE_DIR_NAME
from github_pixel_artworks.identity import Identity

PROJECT_ROOT = Path(__file__).resolve().parents[1]


IDENTITY = Identity("Test User", "test@example.com")


def ignore(_message: str) -> None:
    pass


def clone_path(clone_root: Path, name: str = "pixel-art") -> Path:
    return clone_root / TARGET_CLONE_DIR_NAME / name


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


class TestProjectRoot:
    def test_finds_this_checkout_from_the_package(self) -> None:
        start = Path(__import__("github_pixel_artworks.art_repo", fromlist=["art_repo"]).__file__)
        assert find_tool_project_root(start.resolve()) == PROJECT_ROOT

    def test_is_none_when_there_is_no_project(self, tmp_path: Path) -> None:
        assert find_tool_project_root(tmp_path) is None

    def test_the_clone_parent_is_target_cloned_repo_under_the_project_root(
        self, clone_root: Path
    ) -> None:
        assert target_clone_parent() == clone_root / TARGET_CLONE_DIR_NAME


class TestUrlClone:
    def test_clones_into_target_cloned_repo_under_the_project_root(
        self, empty_remote: str, clone_root: Path
    ) -> None:
        lines: list[str] = []

        repo = clone_url_target(empty_remote, log=lines.append)

        path = Path(str(repo.working_tree_dir))
        assert path == clone_path(clone_root)
        assert repo.remotes.origin.url == empty_remote
        assert any(str(path) in line for line in lines)

    def test_reuses_a_clean_clone_of_the_same_url(
        self, filled_remote: str, clone_root: Path, tmp_path: Path
    ) -> None:
        first = clone_url_target(filled_remote, log=ignore)
        old = first.head.commit.hexsha
        first.close()
        other = git.Repo.clone_from(filled_remote, tmp_path / "other")
        other.git.commit("--allow-empty", "-m", "ahead", env={**os.environ, **IDENTITY.env()})
        other.git.push("origin", "main")
        new = other.head.commit.hexsha
        other.close()
        lines: list[str] = []

        second = clone_url_target(filled_remote, log=lines.append)

        assert Path(str(second.working_tree_dir)) == clone_path(clone_root, "canvas")
        assert second.head.commit.hexsha == new
        assert second.head.commit.hexsha != old
        assert not has_unpushed_commits(second)
        assert any("Updating the existing clone" in line for line in lines)

    def test_reuses_a_clone_that_still_holds_unpushed_commits(
        self, filled_remote: str, clone_root: Path
    ) -> None:
        first = clone_url_target(filled_remote, log=ignore)
        first.git.commit("--allow-empty", "-m", "local", env={**os.environ, **IDENTITY.env()})
        sha = first.head.commit.hexsha
        first.close()
        lines: list[str] = []

        second = clone_url_target(filled_remote, log=lines.append)

        assert second.head.commit.hexsha == sha
        assert has_unpushed_commits(second)
        assert any("unpushed commits" in line for line in lines)

    def test_refuses_a_dirty_leftover_without_resetting_it(
        self, filled_remote: str, clone_root: Path
    ) -> None:
        first = clone_url_target(filled_remote, log=ignore)
        dirty = Path(str(first.working_tree_dir)) / "notes.txt"
        dirty.write_text("keep me", encoding="utf-8")
        first.close()

        with pytest.raises(RuntimeError, match="uncommitted changes"):
            clone_url_target(filled_remote, log=ignore)

        assert dirty.read_text(encoding="utf-8") == "keep me"

    def test_refuses_a_folder_that_is_not_a_clone_of_the_url(
        self, empty_remote: str, clone_root: Path
    ) -> None:
        path = clone_path(clone_root)
        path.mkdir(parents=True)
        (path / "other.txt").write_text("leave me", encoding="utf-8")

        with pytest.raises(RuntimeError, match="already exists and is not a clone"):
            clone_url_target(empty_remote, log=ignore)

        assert (path / "other.txt").read_text(encoding="utf-8") == "leave me"

    def test_a_failed_clone_does_not_leave_a_partial_folder(
        self, clone_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fail(_url: str, path: str, *_args: object, **_kwargs: object) -> None:
            Path(path).mkdir(parents=True)
            (Path(path) / "partial").write_text("x", encoding="utf-8")
            raise GitCommandError(["git", "clone"], 128)

        monkeypatch.setattr(git.Repo, "clone_from", fail)

        with pytest.raises(GitCommandError):
            clone_url_target("https://github.com/you/pixel-art", log=ignore)

        assert not (clone_root / TARGET_CLONE_DIR_NAME).exists()

    def test_a_failed_update_leaves_the_clone_and_explains(
        self, filled_remote: str, clone_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        first = clone_url_target(filled_remote, log=ignore)
        first.close()

        def fail(_repo: git.Repo) -> None:
            raise GitCommandError(["git", "fetch"], 1)

        monkeypatch.setattr("github_pixel_artworks.art_repo._refresh_clean_clone", fail)

        with pytest.raises(RuntimeError, match="Could not update the existing clone"):
            clone_url_target(filled_remote, log=ignore)

        assert clone_path(clone_root, "canvas").is_dir()

    def test_treats_an_unreadable_unpushed_check_as_unpushed(
        self, filled_remote: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        first = clone_url_target(filled_remote, log=ignore)
        first.close()

        def fail(_repo: git.Repo) -> bool:
            raise GitCommandError(["git", "rev-list"], 1)

        monkeypatch.setattr("github_pixel_artworks.art_repo.has_unpushed_commits", fail)
        lines: list[str] = []

        clone_url_target(filled_remote, log=lines.append)

        assert any("unpushed commits" in line for line in lines)

    def test_updates_a_clean_clone_when_the_default_branch_is_unknown(
        self, filled_remote: str, clone_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        first = clone_url_target(filled_remote, log=ignore)
        first.close()
        monkeypatch.setattr("github_pixel_artworks.art_repo.default_branch", lambda _repo: None)
        lines: list[str] = []

        second = clone_url_target(filled_remote, log=lines.append)

        assert Path(str(second.working_tree_dir)) == clone_path(clone_root, "canvas")
        assert any("Updating the existing clone" in line for line in lines)

    def test_counts_commits_not_on_the_remote(self, filled_remote: str) -> None:
        repo = clone_url_target(filled_remote, log=ignore)
        assert not has_unpushed_commits(repo)

        repo.git.commit("--allow-empty", "-m", "local", env={**os.environ, **IDENTITY.env()})

        assert has_unpushed_commits(repo)

    def test_remove_tree_deletes_read_only_files_and_folders(self, tmp_path: Path) -> None:
        folder = tmp_path / "clone" / ".git" / "objects"
        folder.mkdir(parents=True)
        (folder / "pack").write_text("x", encoding="utf-8")
        (folder / "pack").chmod(stat.S_IREAD)
        folder.chmod(stat.S_IREAD | stat.S_IEXEC)

        remove_tree(tmp_path / "clone")

        assert not (tmp_path / "clone").exists()

    def test_remove_dir_if_empty_only_removes_the_clone_parent(self, tmp_path: Path) -> None:
        parent = tmp_path / TARGET_CLONE_DIR_NAME
        parent.mkdir()
        other = tmp_path / "keep-me"
        other.mkdir()

        remove_dir_if_empty(parent)
        remove_dir_if_empty(other)

        assert not parent.exists()
        assert other.is_dir()

    def test_remove_dir_if_empty_keeps_a_non_empty_clone_parent(self, tmp_path: Path) -> None:
        parent = tmp_path / TARGET_CLONE_DIR_NAME
        parent.mkdir()
        (parent / "keep").mkdir()

        remove_dir_if_empty(parent)

        assert parent.is_dir()


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

    def test_a_clone_inside_the_project_is_not_the_tool_checkout(
        self, empty_remote: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = tmp_path / "github_pixel_artworks"
        package = root / "src" / "github_pixel_artworks"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("", encoding="utf-8")
        (root / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
        monkeypatch.setattr("github_pixel_artworks.art_repo.tool_project_root", lambda: root)

        repo = clone_url_target(empty_remote, log=ignore)
        path = Path(str(repo.working_tree_dir))

        assert path == root / TARGET_CLONE_DIR_NAME / "pixel-art"
        assert path.is_relative_to(root)
        assert is_tool_checkout(root)
        assert not is_tool_checkout(path)


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
