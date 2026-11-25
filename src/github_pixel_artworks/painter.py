"""Turn an artwork into backdated, empty git commits."""

import os
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

import git
from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError

from .artwork import DAYS_PER_WEEK, MAX_WEEKS, Grid, count_commits, validate_grid
from .dates import get_first_sunday_of_year, pixel_timestamp
from .github import resolve_github_repo_url

type Log = Callable[[str], None]

DEFAULT_ORPHAN_BRANCH = "pixel-art"
PROGRESS_EVERY = 10
"""Log a progress line every this many commits."""

_FILLED_PIXEL = "#"
_EMPTY_PIXEL = "."


def preview(grid: Grid, start_date: datetime, multiplier: int) -> str:
    """Return a text preview of ``grid`` with its date span and commit count."""
    width = len(grid[0])
    end_date = start_date + timedelta(weeks=width - 1, days=DAYS_PER_WEEK - 1)
    rows = ["".join(_FILLED_PIXEL if level else _EMPTY_PIXEL for level in row) for row in grid]
    return "\n".join(
        [
            *rows,
            "",
            f"Span: {start_date.date()} (Sun) to {end_date.date()} (Sat)",
            f"Total weeks: {width} | Multiplier: {multiplier}",
            f"Total commits that will be created: {count_commits(grid, multiplier)}",
        ]
    )


def apply_drawing(
    grid: Grid,
    year: int | None = None,
    start_date: datetime | None = None,
    offset_weeks: int = 0,
    target_repo: str = ".",
    multiplier: int = 1,
    in_place: bool = True,
    force: bool = False,
    art_branch: str | None = None,
    username: str | None = None,
    branch: str = DEFAULT_ORPHAN_BRANCH,
    log: Log = print,
) -> int:
    """Create the backdated commits that draw ``grid`` and return how many were made.

    The start is ``start_date`` or, if that is None, the first Sunday of ``year``
    plus ``offset_weeks`` (at most ``MAX_WEEKS``; negative values reach into the
    previous year). Each pixel is committed ``level * multiplier`` times at 12:00
    UTC on its day.

    Where the commits go:

    - ``art_branch``: on that branch, created from HEAD if it does not exist.
      Uncommitted changes (untracked files included) are stashed first; the
      original branch and the changes are always restored afterwards.
    - otherwise ``in_place=True``: on the current branch.
    - otherwise: on a new orphan branch ``branch`` whose only file is a README.
      Tracked files leave the working tree; untracked and ignored files stay.

    Raises:
        ValueError: for an invalid grid, multiplier, offset, branch name or
            missing start.
        RuntimeError: if ``target_repo`` is not a git repository, has
            uncommitted changes (unless ``force``), or the orphan branch exists.
    """
    if not grid or not grid[0]:
        log("Nothing to do (empty grid).")
        return 0
    validate_grid(grid)
    if multiplier < 1:
        raise ValueError(f"multiplier must be at least 1 (got {multiplier}).")
    if offset_weeks > MAX_WEEKS:
        raise ValueError(f"offset_weeks must not exceed {MAX_WEEKS} (got {offset_weeks}).")
    start_date = _resolve_start_date(year, start_date, offset_weeks)

    log("=== GitHub Pixel Art ===")
    log(preview(grid, start_date, multiplier))
    log("")

    repo = _open_repo(target_repo)
    _validate_branch_name(repo, art_branch or (None if in_place else branch))

    original_ref = _current_ref(repo)
    stashed = False
    try:
        if art_branch:
            stashed = _stash_changes(repo, art_branch, log)
            _switch_to_branch(repo, art_branch, log)
        _ensure_clean(repo, force)
        if art_branch or in_place:
            log(f"Committing on the current branch ({_branch_label(repo)}).")
        else:
            _start_orphan_branch(repo, branch, username, log)

        log("Creating backdated commits...")
        total = _commit_artwork(repo, grid, start_date, multiplier, log)
        log(f"Created {total} backdated commits on branch {_branch_label(repo)}.")
    finally:
        if art_branch:
            _restore(repo, original_ref, stashed, log)
    return total


def _resolve_start_date(
    year: int | None, start_date: datetime | None, offset_weeks: int
) -> datetime:
    if start_date is not None:
        return start_date
    if year is None:
        raise ValueError("Either year or start_date must be provided to apply_drawing")
    return get_first_sunday_of_year(year) + timedelta(weeks=offset_weeks)


def _open_repo(path: str) -> git.Repo:
    try:
        return git.Repo(path)
    except InvalidGitRepositoryError, NoSuchPathError:
        raise RuntimeError(f"{path} is not a git repository") from None


def _validate_branch_name(repo: git.Repo, name: str | None) -> None:
    """Raise ValueError unless ``name`` (if given) is a valid branch name, not an option."""
    if name is None:
        return
    if name.startswith("-"):
        raise ValueError(f"Invalid branch name: {name!r}")
    try:
        repo.git.check_ref_format("--branch", name)
    except GitCommandError:
        raise ValueError(f"Invalid branch name: {name!r}") from None


def _current_ref(repo: git.Repo) -> str:
    """Return the current branch name, or the commit SHA when HEAD is detached."""
    return repo.head.commit.hexsha if repo.head.is_detached else repo.active_branch.name


def _branch_label(repo: git.Repo) -> str:
    return "detached HEAD" if repo.head.is_detached else repo.active_branch.name


def _stash_changes(repo: git.Repo, art_branch: str, log: Log) -> bool:
    """Stash uncommitted changes, untracked files included; return whether anything was stashed."""
    if not repo.is_dirty(untracked_files=True):
        return False
    log("Stashing uncommitted changes...")
    repo.git.stash("push", "--include-untracked", "-m", f"auto-stash before art on {art_branch}")
    return True


def _switch_to_branch(repo: git.Repo, name: str, log: Log) -> None:
    """Check out ``name``, creating it from HEAD if needed (an existing branch is kept as is)."""
    if name in repo.heads:
        repo.git.checkout(name)
    else:
        repo.git.checkout("-b", name)
    log(f"Switched to art branch '{name}'.")


def _ensure_clean(repo: git.Repo, force: bool) -> None:
    if not force and repo.is_dirty(untracked_files=True):
        raise RuntimeError(
            "Target repo has uncommitted changes or untracked files. "
            "Commit or stash them first, or run with force (CLI: --force)."
        )


def _restore(repo: git.Repo, original_ref: str, stashed: bool, log: Log) -> None:
    """Return to ``original_ref`` and pop the stash; failures are logged, not raised."""
    if _current_ref(repo) != original_ref:
        try:
            repo.git.checkout(original_ref)
            log(f"Switched back to '{original_ref}'.")
        except GitCommandError as error:
            log(f"Warning: could not switch back to '{original_ref}': {error}")
    if stashed:
        try:
            repo.git.stash("pop")
            log("Restored stashed changes.")
        except GitCommandError as error:
            log(f"Warning: could not pop the stash (run `git stash pop` manually): {error}")


def _start_orphan_branch(repo: git.Repo, name: str, username: str | None, log: Log) -> None:
    """Switch to a new orphan branch whose only tracked file is a short README."""
    if name in repo.heads:
        raise RuntimeError(
            f"Branch '{name}' already exists. Pick another branch name "
            "or use art_branch to add commits to an existing art branch."
        )
    log(f"Creating orphan branch '{name}'...")
    repo.git.checkout("--orphan", name)
    if repo.git.ls_files():
        repo.git.rm("-r", "-f", "--quiet", ".")

    readme = Path(str(repo.working_tree_dir)) / "README.md"
    readme.write_text(_orphan_readme(repo, name, username), encoding="utf-8")
    repo.index.add(["README.md"])
    repo.index.commit("chore: initialize pixel-art branch")


def _orphan_readme(repo: git.Repo, branch: str, username: str | None) -> str:
    repo_url = resolve_github_repo_url(repo, username=username)
    lines = [
        "# GitHub Pixel Art",
        "",
        f"Generated on {datetime.now().isoformat()} using github-pixel-artworks",
        *([f"Repo: {repo_url}"] if repo_url else []),
        f"Branch: {branch}",
    ]
    return "\n".join(lines) + "\n"


def _commit_artwork(
    repo: git.Repo, grid: Grid, start_date: datetime, multiplier: int, log: Log
) -> int:
    """Create every pixel's commits, column by column; return the number created."""
    total = 0
    for week in range(len(grid[0])):
        for day in range(DAYS_PER_WEEK):
            commits = grid[day][week] * multiplier
            when = pixel_timestamp(start_date, week, day)
            for index in range(1, commits + 1):
                _commit_pixel(repo, when, f"pixel art ({day},{week}) [{index}/{commits}]")
                total += 1
                if total % PROGRESS_EVERY == 0:
                    log(f"  ... {total} commits so far")
    return total


def _commit_pixel(repo: git.Repo, when: datetime, message: str) -> None:
    """Create one empty commit authored and committed at ``when``.

    ``when`` is timezone-aware, so git never applies the local timezone. Hooks are
    skipped: the target repo's pre-commit checks would otherwise run per pixel.
    """
    stamp = when.isoformat()
    env = {**os.environ, "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
    repo.git.commit("--allow-empty", "--no-verify", "-m", message, env=env)
