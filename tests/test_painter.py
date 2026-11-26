"""apply_drawing and preview, end to end against a temporary git repository."""

from datetime import UTC, datetime
from pathlib import Path

import git
import pytest

from github_pixel_artworks.artwork import MAX_WEEKS
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


class TestInPlace:
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

    def test_rerun_adds_to_the_existing_branch(self, git_repo: git.Repo) -> None:
        draw(git_repo, art_branch="artworks-2026")

        draw(git_repo, art_branch="artworks-2026")

        assert len(art_commits(git_repo, "artworks-2026")) == 4

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


class TestOrphanBranch:
    def test_keeps_ignored_files_and_tracks_only_a_readme(self, git_repo: git.Repo) -> None:
        root = root_of(git_repo)
        (root / ".env").write_text("SECRET=1\n", encoding="utf-8")  # ignored, so "clean"

        count = draw(git_repo, in_place=False, branch="my-art")

        assert count == 2
        assert git_repo.active_branch.name == "my-art"
        assert (root / ".env").read_text(encoding="utf-8") == "SECRET=1\n"
        assert git_repo.git.ls_files().splitlines() == ["README.md"]
        readme = (root / "README.md").read_text(encoding="utf-8")
        assert "Repo: https://github.com/someone/canvas" in readme
        assert "source.py" in git_repo.git.ls_tree("--name-only", "main").splitlines()

    def test_refuses_an_existing_branch(self, git_repo: git.Repo) -> None:
        git_repo.create_head("pixel-art")

        with pytest.raises(RuntimeError, match="already exists"):
            draw(git_repo, in_place=False)

        assert git_repo.active_branch.name == "main"
