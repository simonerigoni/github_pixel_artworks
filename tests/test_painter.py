"""apply_drawing and preview, end to end against a temporary git repository."""

from datetime import UTC, datetime
from pathlib import Path

import git
import pytest

from github_pixel_artworks.config import CLONE_TEMP_PREFIX, MAX_WEEKS
from github_pixel_artworks.identity import MissingIdentityError
from github_pixel_artworks.painter import apply_drawing, preview

ONE_PIXEL_LEVEL_TWO = [[2], [0], [0], [0], [0], [0], [0]]
"""A single level-2 pixel on the first Sunday."""


def ignore(_message: str) -> None:
    pass


def root_of(repo: git.Repo) -> Path:
    return Path(str(repo.working_tree_dir))


def art_commits(repo: git.Repo, rev: str) -> list[git.Commit]:
    return [c for c in repo.iter_commits(rev) if str(c.message).startswith("pixel art")]


def draw(repo: git.Repo, **kwargs: object) -> int:
    options: dict = {"grid": ONE_PIXEL_LEVEL_TWO, "year": 2026, "log": ignore} | kwargs
    return apply_drawing(target_repo=str(root_of(repo)), **options)


def test_preview_shows_span_multiplier_and_commit_count() -> None:
    grid = [[1, 0], [0, 1], [0, 0], [0, 0], [0, 0], [0, 0], [0, 0]]

    text = preview(grid, datetime(2026, 1, 4), multiplier=3)

    assert text.splitlines()[:2] == ["#.", ".#"]
    assert "Span: 2026-01-04 (Sun) to 2026-01-17 (Sat)" in text
    assert "Total weeks: 2 | Multiplier: 3" in text
    assert "Total commits that will be created: 6" in text


class TestDefaultBranch:
    def test_commits_each_pixel_on_its_utc_day(self, git_repo: git.Repo) -> None:
        count = draw(git_repo, start_date=datetime(2026, 1, 4))

        commits = art_commits(git_repo, "main")
        assert count == len(commits) == 2
        for commit in commits:
            assert commit.authored_datetime.astimezone(UTC).date().isoformat() == "2026-01-04"
            assert commit.committed_datetime.astimezone(UTC).date().isoformat() == "2026-01-04"

    def test_multiplier_multiplies_the_commits(self, git_repo: git.Repo) -> None:
        assert draw(git_repo, multiplier=3) == 6

    @pytest.mark.parametrize("offset", [MAX_WEEKS, -3])
    def test_accepts_offsets_up_to_a_year_and_negative(
        self, git_repo: git.Repo, offset: int
    ) -> None:
        assert draw(git_repo, offset_weeks=offset) == 2

    def test_empty_grid_does_nothing(self, git_repo: git.Repo) -> None:
        assert draw(git_repo, grid=[[]] * 7) == 0
        assert art_commits(git_repo, "main") == []

    def test_refuses_a_branch_that_is_not_the_default(
        self, tmp_path: Path, filled_remote: str
    ) -> None:
        clone = git.Repo.clone_from(filled_remote, tmp_path / "clone")
        clone.git.checkout("-b", "feature")

        with pytest.raises(RuntimeError, match="not the default branch"):
            draw(clone)

        assert art_commits(clone, "feature") == []

    def test_refuses_the_tool_checkout(self, git_repo: git.Repo) -> None:
        package = root_of(git_repo) / "src" / "github_pixel_artworks"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("", encoding="utf-8")
        git_repo.index.add(["src/github_pixel_artworks/__init__.py"])
        git_repo.index.commit("the tool itself")

        with pytest.raises(RuntimeError, match="github-pixel-artworks checkout"):
            draw(git_repo)

        assert art_commits(git_repo, "main") == []


class TestEmptyCommits:
    def test_art_commits_change_no_files_and_keep_staged_work(self, git_repo: git.Repo) -> None:
        initial_tree = git_repo.head.commit.tree
        root = root_of(git_repo)
        (root / "source.py").write_text("print('staged work')\n", encoding="utf-8")
        git_repo.index.add(["source.py"])

        draw(git_repo, force=True)

        assert {commit.tree for commit in art_commits(git_repo, "main")} == {initial_tree}
        assert git_repo.git.diff("--cached", "--name-only") == "source.py"
        assert (root / "source.py").read_text(encoding="utf-8") == "print('staged work')\n"


class TestRerun:
    def test_the_same_drawing_adds_nothing(self, git_repo: git.Repo) -> None:
        draw(git_repo)
        lines: list[str] = []

        count = draw(git_repo, log=lines.append)

        assert count == 0
        assert len(art_commits(git_repo, "main")) == 2
        assert any("2 already present" in line for line in lines)

    def test_a_higher_multiplier_adds_only_the_difference(self, git_repo: git.Repo) -> None:
        draw(git_repo)

        count = draw(git_repo, multiplier=3)

        assert count == 4
        assert len(art_commits(git_repo, "main")) == 6

    def test_dry_run_reports_the_plan_without_committing(self, git_repo: git.Repo) -> None:
        head = git_repo.head.commit
        lines: list[str] = []

        count = draw(git_repo, dry_run=True, log=lines.append)

        assert count == 2
        assert git_repo.head.commit == head
        assert any("Dry run" in line and "2 commits" in line for line in lines)


class TestNewArtRepository:
    def test_clones_an_empty_repository_draws_and_pushes(
        self,
        tmp_path: Path,
        empty_remote: str,
        git_identity: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(tmp_path)

        count = apply_drawing(
            ONE_PIXEL_LEVEL_TWO, year=2026, target_repo=empty_remote, push=True, log=ignore
        )

        remote = git.Repo(empty_remote.removeprefix("file://"))
        assert count == 2
        assert len(art_commits(remote, "main")) == 2

    def test_without_push_tells_how_to_push(
        self, tmp_path: Path, empty_remote: str, git_identity: None
    ) -> None:
        lines: list[str] = []
        clone = tmp_path / "pixel-art"
        git.Repo.clone_from(empty_remote, clone)

        apply_drawing(ONE_PIXEL_LEVEL_TWO, year=2026, target_repo=str(clone), log=lines.append)

        assert f"git -C {clone} push -u origin main" in "\n".join(lines)


def temp_clones(temp_root: Path) -> list[Path]:
    return sorted(temp_root.glob(f"{CLONE_TEMP_PREFIX}*"))


def draw_url(url: str, **kwargs: object) -> int:
    options: dict = {"grid": ONE_PIXEL_LEVEL_TWO, "year": 2026, "log": ignore} | kwargs
    return apply_drawing(target_repo=url, **options)


class TestIdentity:
    def test_the_art_uses_the_identity_of_the_folder_the_tool_runs_in(
        self, source_checkout: Path, empty_remote: str
    ) -> None:
        lines: list[str] = []

        count = draw_url(empty_remote, push=True, log=lines.append)

        remote = git.Repo(empty_remote.removeprefix("file://"))
        commits = art_commits(remote, "main")
        assert count == len(commits) == 2
        for commit in commits:
            assert (commit.author.name, commit.author.email) == (
                "Source User",
                "source@example.com",
            )
            assert commit.committer.email == "source@example.com"
        assert not any("not set" in line for line in lines)
        assert any("Source User <source@example.com>" in line for line in lines)

    def test_the_clone_is_not_inside_the_tool_checkout(
        self, source_checkout: Path, empty_remote: str, temp_root: Path
    ) -> None:
        draw_url(empty_remote, keep_clone=True)

        [clone] = temp_clones(temp_root)
        assert not clone.is_relative_to(source_checkout)
        assert not (source_checkout / "pixel-art").exists()
        assert not (source_checkout / "sub" / "pixel-art").exists()

    def test_the_target_repository_identity_wins(
        self, source_checkout: Path, tmp_path: Path, filled_remote: str
    ) -> None:
        clone = git.Repo.clone_from(filled_remote, tmp_path / "art")
        with clone.config_writer() as cw:
            cw.set_value("user", "email", "target@example.com")

        draw(clone)

        assert {c.author.email for c in art_commits(clone, "main")} == {"target@example.com"}

    def test_fails_before_cloning_without_any_identity(
        self, empty_remote: str, temp_root: Path
    ) -> None:
        with pytest.raises(MissingIdentityError, match="git config --global user.email"):
            draw_url(empty_remote)

        assert temp_clones(temp_root) == []

    def test_fails_before_committing_when_the_target_has_no_identity(
        self, tmp_path: Path, filled_remote: str
    ) -> None:
        clone = git.Repo.clone_from(filled_remote, tmp_path / "art")
        head = clone.head.commit

        with pytest.raises(MissingIdentityError):
            draw(clone)

        assert clone.head.commit == head


class TestTemporaryClone:
    def test_is_deleted_once_the_art_is_pushed(
        self, empty_remote: str, git_identity: None, temp_root: Path
    ) -> None:
        lines: list[str] = []

        draw_url(empty_remote, push=True, log=lines.append)

        assert temp_clones(temp_root) == []
        assert any("Removed the temporary clone" in line for line in lines)

    def test_is_kept_while_its_art_commits_are_unpushed(
        self, empty_remote: str, git_identity: None, temp_root: Path
    ) -> None:
        lines: list[str] = []
        kept: list[Path] = []

        draw_url(empty_remote, log=lines.append, on_clone_kept=kept.append)

        [folder] = temp_clones(temp_root)
        clone = folder / "pixel-art"
        assert kept == [clone]
        assert len(art_commits(git.Repo(clone), "main")) == 2
        text = "\n".join(lines)
        assert f"git -C {clone} push -u origin main" in text
        assert f"Kept the temporary clone at {clone}" in text

    def test_is_kept_when_the_push_fails(
        self,
        empty_remote: str,
        git_identity: None,
        temp_root: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def failing_push(*_args: object) -> None:
            raise RuntimeError("push rejected")

        monkeypatch.setattr("github_pixel_artworks.painter.push_branch", failing_push)
        lines: list[str] = []

        with pytest.raises(RuntimeError, match="push rejected"):
            draw_url(empty_remote, push=True, log=lines.append)

        [folder] = temp_clones(temp_root)
        assert any(f"Kept the temporary clone at {folder / 'pixel-art'}" in line for line in lines)

    def test_is_deleted_when_drawing_fails_before_any_commit(
        self, empty_remote: str, git_identity: None, temp_root: Path
    ) -> None:
        with pytest.raises(ValueError):
            draw_url(empty_remote, art_branch="bad..name")

        assert temp_clones(temp_root) == []

    def test_is_deleted_after_a_dry_run(
        self, empty_remote: str, git_identity: None, temp_root: Path
    ) -> None:
        assert draw_url(empty_remote, dry_run=True) == 2

        assert temp_clones(temp_root) == []

    def test_is_deleted_when_the_art_is_already_published(
        self, empty_remote: str, git_identity: None, temp_root: Path
    ) -> None:
        draw_url(empty_remote, push=True)

        assert draw_url(empty_remote) == 0
        assert temp_clones(temp_root) == []

    def test_keep_clone_keeps_it_after_a_push(
        self, empty_remote: str, git_identity: None, temp_root: Path
    ) -> None:
        draw_url(empty_remote, push=True, keep_clone=True)

        assert len(temp_clones(temp_root)) == 1

    def test_a_local_target_is_never_deleted(
        self, tmp_path: Path, filled_remote: str, git_identity: None
    ) -> None:
        clone = git.Repo.clone_from(filled_remote, tmp_path / "art")

        draw(clone, push=True)

        assert (tmp_path / "art" / ".git").is_dir()


class TestProfileWarnings:
    def test_warns_about_a_noreply_email_of_another_account(self, git_repo: git.Repo) -> None:
        with git_repo.config_writer() as cw:
            cw.set_value("user", "email", "123+other@users.noreply.github.com")
        lines: list[str] = []

        draw(git_repo, log=lines.append)

        assert any(line.startswith("Warning:") and "'other'" in line for line in lines)

    def test_warns_when_the_repository_is_a_fork(
        self, git_repo: git.Repo, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("github_pixel_artworks.painter.fetch_is_fork", lambda _o, _n: True)
        lines: list[str] = []

        draw(git_repo, log=lines.append)

        assert any(line.startswith("Warning:") and "fork" in line for line in lines)

    def test_a_matching_setup_has_no_warnings(self, git_repo: git.Repo) -> None:
        lines: list[str] = []

        draw(git_repo, log=lines.append)

        assert not any(line.startswith("Warning:") for line in lines)


class TestValidation:
    @pytest.mark.parametrize(
        ("options", "message"),
        [
            ({"multiplier": 0}, "multiplier"),
            ({"offset_weeks": MAX_WEEKS + 1}, str(MAX_WEEKS)),
            ({"year": None}, "year or start_date"),
            ({"grid": [[1, 1]] * 6 + [[1]]}, "same width"),
        ],
    )
    def test_rejects_bad_input_before_touching_the_repo(
        self, git_repo: git.Repo, options: dict, message: str
    ) -> None:
        with pytest.raises(ValueError, match=message):
            draw(git_repo, **options)

        assert len(list(git_repo.iter_commits())) == 1

    def test_rejects_option_like_branch_names(self, git_repo: git.Repo) -> None:
        with pytest.raises(ValueError, match="branch name"):
            draw(git_repo, art_branch="--orphan")

    def test_refuses_a_dirty_repo_without_force(self, git_repo: git.Repo) -> None:
        (root_of(git_repo) / "new.txt").write_text("x", encoding="utf-8")

        with pytest.raises(RuntimeError, match="uncommitted"):
            draw(git_repo)

    def test_force_allows_a_dirty_repo(self, git_repo: git.Repo) -> None:
        (root_of(git_repo) / "new.txt").write_text("x", encoding="utf-8")

        assert draw(git_repo, force=True) == 2

    def test_rejects_a_directory_that_is_not_a_repo(self, tmp_path: Path) -> None:
        with pytest.raises(RuntimeError, match="not a git repository"):
            apply_drawing(ONE_PIXEL_LEVEL_TWO, year=2026, target_repo=str(tmp_path), log=ignore)


class TestArtBranch:
    def test_stashes_changes_and_returns_to_the_original_branch(self, git_repo: git.Repo) -> None:
        root = root_of(git_repo)
        (root / "source.py").write_text("print('work in progress')\n", encoding="utf-8")
        (root / "notes.txt").write_text("untracked notes\n", encoding="utf-8")

        count = draw(git_repo, art_branch="artworks-2026")

        assert count == 2
        assert len(art_commits(git_repo, "artworks-2026")) == 2
        assert art_commits(git_repo, "main") == []
        assert git_repo.active_branch.name == "main"
        assert (root / "source.py").read_text(encoding="utf-8") == "print('work in progress')\n"
        assert (root / "notes.txt").read_text(encoding="utf-8") == "untracked notes\n"
        assert git_repo.git.stash("list") == ""

    def test_warns_that_the_branch_must_become_the_default(self, git_repo: git.Repo) -> None:
        lines: list[str] = []

        draw(git_repo, art_branch="artworks-2026", log=lines.append)

        assert any("default branch" in line for line in lines if line.startswith("Warning:"))

    def test_rerun_on_the_same_branch_adds_nothing(self, git_repo: git.Repo) -> None:
        draw(git_repo, art_branch="artworks-2026")

        count = draw(git_repo, art_branch="artworks-2026")

        assert count == 0
        assert len(art_commits(git_repo, "artworks-2026")) == 2

    def test_restores_branch_and_changes_when_drawing_fails(
        self, git_repo: git.Repo, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = root_of(git_repo)
        (root / "source.py").write_text("print('wip')\n", encoding="utf-8")

        def fail(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("commit failed")

        monkeypatch.setattr("github_pixel_artworks.painter._commit_pixel", fail)

        with pytest.raises(RuntimeError, match="commit failed"):
            draw(git_repo, art_branch="artworks-2026")

        assert git_repo.active_branch.name == "main"
        assert (root / "source.py").read_text(encoding="utf-8") == "print('wip')\n"
