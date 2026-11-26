"""Turn an artwork into backdated, empty git commits."""

import os
from datetime import datetime, timedelta
from pathlib import Path

import git
from git.exc import GitCommandError

from .art_repo import Log, default_branch, is_tool_checkout, open_art_repo, push_branch
from .artwork import DAYS_PER_WEEK, MAX_WEEKS, Grid, count_commits, validate_grid
from .dates import get_first_sunday_of_year, pixel_timestamp
from .github import commit_email_warning, fetch_is_fork, github_slug

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
    *,
    target_repo: str,
    year: int | None = None,
    start_date: datetime | None = None,
    offset_weeks: int = 0,
    multiplier: int = 1,
    art_branch: str | None = None,
    username: str | None = None,
    push: bool = False,
    force: bool = False,
    log: Log = print,
) -> int:
    """Create the backdated commits that draw ``grid`` and return how many were made.

    ``target_repo`` is the art repository: a local path, or a URL that is cloned
    into the working directory. The start is ``start_date`` or, if that is None,
    the first Sunday of ``year`` plus ``offset_weeks`` (at most ``MAX_WEEKS``;
    negative values reach into the previous year). Each pixel is committed
    ``level * multiplier`` times at 12:00 UTC on its day.

    By default the commits go on the repository's default branch, the only place
    GitHub counts them. A checkout of this tool is refused. With ``art_branch``
    (advanced) they go on that branch instead, created from HEAD if missing;
    uncommitted changes are stashed and the original branch and changes are
    restored afterwards. ``push`` pushes the branch to ``origin`` at the end.

    Warnings are logged when the commit email or a fork would keep the art off
    the profile of ``username`` (default: the owner of ``origin``).

    Raises:
        ValueError: for an invalid grid, multiplier, offset, branch name or
            missing start.
        RuntimeError: if the target is not a git repository, is this tool's
            checkout, is not on its default branch, or has uncommitted changes
            (unless ``force``).
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

    repo = open_art_repo(target_repo, log)
    root = Path(str(repo.working_tree_dir))
    if art_branch:
        _validate_branch_name(repo, art_branch)
        log(
            f"Warning: commits on '{art_branch}' only show on your profile once they are on "
            "the repository's default branch: merge the branch or make it the default."
        )
        branch = art_branch
    else:
        _refuse_tool_checkout(root)
        branch = _require_default_branch(repo, root)
    for warning in _profile_warnings(repo, username):
        log(f"Warning: {warning}")

    original_ref = _current_ref(repo) if art_branch else None
    stashed = False
    try:
        if art_branch:
            stashed = _stash_changes(repo, art_branch, log)
            _switch_to_branch(repo, art_branch, log)
        _ensure_clean(repo, force)
        log(f"Creating backdated commits on '{branch}'...")
        total = _commit_artwork(repo, grid, start_date, multiplier, log)
        log(f"Created {total} backdated commits on branch {branch}.")
    finally:
        if original_ref is not None:
            _restore(repo, original_ref, stashed, log)

    if push:
        push_branch(repo, branch, log)
    else:
        log(f"To publish the art, run: git -C {root} push -u origin {branch}")
    return total


def _resolve_start_date(
    year: int | None, start_date: datetime | None, offset_weeks: int
) -> datetime:
    if start_date is not None:
        return start_date
    if year is None:
        raise ValueError("Either year or start_date must be provided to apply_drawing")
    return get_first_sunday_of_year(year) + timedelta(weeks=offset_weeks)


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


def _refuse_tool_checkout(root: Path) -> None:
    if is_tool_checkout(root):
        raise RuntimeError(
            f"{root} is a github-pixel-artworks checkout. Art drawn here would not show on "
            "your profile and would fill the tool's history with fake commits. Create an "
            "empty repository on GitHub (for example <you>/pixel-art) and pass it as the target."
        )


def _require_default_branch(repo: git.Repo, root: Path) -> str:
    """Return the current branch, which must be the default branch when that is known."""
    if repo.head.is_detached:
        raise RuntimeError(f"HEAD is detached in {root}. Check out its default branch first.")
    current = repo.active_branch.name
    default = default_branch(repo)
    if default and current != default:
        raise RuntimeError(
            f"'{current}' is not the default branch ('{default}') of {root}, so GitHub "
            f"would not count the commits. Check out '{default}', or use an art branch."
        )
    return current


def _profile_warnings(repo: git.Repo, username: str | None) -> list[str]:
    """Return why the commits might not show on the profile of ``username``."""
    slug = github_slug(repo.remotes.origin.url) if "origin" in repo.remotes else None
    login = username or (slug[0] if slug else None)
    warnings = []
    if email_warning := commit_email_warning(_commit_email(repo), login):
        warnings.append(email_warning)
    if slug and fetch_is_fork(*slug):
        warnings.append(
            f"{slug[0]}/{slug[1]} is a fork, and GitHub does not count commits made in "
            "forks. Create a new repository for the art instead."
        )
    return warnings


def _commit_email(repo: git.Repo) -> str | None:
    """Return the email git will put on the commits, if it is configured."""
    if email := os.environ.get("GIT_AUTHOR_EMAIL"):
        return email
    try:
        return repo.git.config("--get", "user.email") or None
    except GitCommandError:
        return None


def _current_ref(repo: git.Repo) -> str:
    """Return the current branch name, or the commit SHA when HEAD is detached."""
    return repo.head.commit.hexsha if repo.head.is_detached else repo.active_branch.name


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
