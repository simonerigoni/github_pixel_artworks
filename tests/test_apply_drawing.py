"""End-to-end tests for apply_drawing against a real (temporary) git repository."""

from datetime import UTC, datetime
from pathlib import Path

import git
import pytest

from github_pixel_artworks.core import apply_drawing

# One pixel on the first Sunday column (row 0 = Sunday), level 2.
ONE_PIXEL = [[2], [0], [0], [0], [0], [0], [0]]


def _root(repo: git.Repo) -> Path:
    return Path(str(repo.working_tree_dir))


def _art_commits(repo: git.Repo, rev: str) -> list[git.Commit]:
    return [c for c in repo.iter_commits(rev) if str(c.message).startswith("pixel art")]


def _quiet(_msg: str) -> None:
    pass


def test_in_place_creates_commits_on_the_right_utc_day(git_repo: git.Repo) -> None:
    start = datetime(2026, 1, 4)  # Sunday, naive midnight
    n = apply_drawing(ONE_PIXEL, start_date=start, target_repo=str(_root(git_repo)), log=_quiet)
    assert n == 2
    commits = _art_commits(git_repo, "main")
    assert len(commits) == 2
    for c in commits:
        # GitHub buckets contributions by UTC day: must stay on 2026-01-04 whatever the local TZ.
        assert c.authored_datetime.astimezone(UTC).date().isoformat() == "2026-01-04"
        assert c.committed_datetime.astimezone(UTC).date().isoformat() == "2026-01-04"


def test_rejects_multiplier_below_one(git_repo: git.Repo) -> None:
    with pytest.raises(ValueError, match="multiplier"):
        apply_drawing(ONE_PIXEL, year=2026, multiplier=0, target_repo=str(_root(git_repo)))


def test_dirty_repo_without_force_raises(git_repo: git.Repo) -> None:
    (_root(git_repo) / "new.txt").write_text("x", encoding="utf-8")
    with pytest.raises(RuntimeError, match="uncommitted"):
        apply_drawing(ONE_PIXEL, year=2026, target_repo=str(_root(git_repo)), log=_quiet)


def test_not_a_repo_raises(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="not a git repository"):
        apply_drawing(ONE_PIXEL, year=2026, target_repo=str(tmp_path), log=_quiet)


def test_art_branch_stashes_untracked_and_returns_to_original_branch(git_repo: git.Repo) -> None:
    root = _root(git_repo)
    (root / "source.py").write_text("print('work in progress')\n", encoding="utf-8")
    (root / "notes.txt").write_text("untracked notes\n", encoding="utf-8")

    n = apply_drawing(
        ONE_PIXEL, year=2026, target_repo=str(root), art_branch="artworks-2026", log=_quiet
    )

    assert n == 2
    assert len(_art_commits(git_repo, "artworks-2026")) == 2
    assert _art_commits(git_repo, "main") == []
    # Back where we started, with the work-in-progress restored (tracked and untracked).
    assert git_repo.active_branch.name == "main"
    assert (root / "source.py").read_text(encoding="utf-8") == "print('work in progress')\n"
    assert (root / "notes.txt").read_text(encoding="utf-8") == "untracked notes\n"
    assert git_repo.git.stash("list") == ""


def test_art_branch_rerun_keeps_previous_art(git_repo: git.Repo) -> None:
    root = str(_root(git_repo))
    apply_drawing(ONE_PIXEL, year=2026, target_repo=root, art_branch="artworks-2026", log=_quiet)
    apply_drawing(ONE_PIXEL, year=2026, target_repo=root, art_branch="artworks-2026", log=_quiet)
    # An existing art branch must be reused, not reset back to the current HEAD.
    assert len(_art_commits(git_repo, "artworks-2026")) == 4


def test_art_branch_restores_state_when_generation_fails(
    git_repo: git.Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root(git_repo)
    (root / "source.py").write_text("print('wip')\n", encoding="utf-8")

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("commit failed")

    monkeypatch.setattr("github_pixel_artworks.core._commit_pixel", boom)
    with pytest.raises(RuntimeError, match="commit failed"):
        apply_drawing(
            ONE_PIXEL, year=2026, target_repo=str(root), art_branch="artworks-2026", log=_quiet
        )
    assert git_repo.active_branch.name == "main"
    assert (root / "source.py").read_text(encoding="utf-8") == "print('wip')\n"


def test_art_branch_rejects_option_like_names(git_repo: git.Repo) -> None:
    with pytest.raises(ValueError, match="branch name"):
        apply_drawing(
            ONE_PIXEL,
            year=2026,
            target_repo=str(_root(git_repo)),
            art_branch="--orphan",
            log=_quiet,
        )


def test_orphan_mode_keeps_ignored_files_and_uses_given_branch(git_repo: git.Repo) -> None:
    root = _root(git_repo)
    (root / ".env").write_text("SECRET=1\n", encoding="utf-8")  # ignored, so repo is "clean"

    n = apply_drawing(
        ONE_PIXEL,
        year=2026,
        target_repo=str(root),
        in_place=False,
        branch="my-art",
        log=_quiet,
    )

    assert n == 2
    assert git_repo.active_branch.name == "my-art"
    # Ignored local files must never be deleted.
    assert (root / ".env").read_text(encoding="utf-8") == "SECRET=1\n"
    # The orphan branch only tracks its README, linking the target repo's remote.
    tracked = git_repo.git.ls_files().splitlines()
    assert tracked == ["README.md"]
    assert "https://github.com/someone/canvas" in (root / "README.md").read_text(encoding="utf-8")
    # The original history is untouched.
    assert "source.py" in git_repo.git.ls_tree("--name-only", "main").splitlines()


def test_orphan_mode_refuses_existing_branch(git_repo: git.Repo) -> None:
    git_repo.create_head("pixel-art")
    with pytest.raises(RuntimeError, match="already exists"):
        apply_drawing(
            ONE_PIXEL, year=2026, target_repo=str(_root(git_repo)), in_place=False, log=_quiet
        )
    assert git_repo.active_branch.name == "main"
