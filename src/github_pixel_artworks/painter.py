"""Turn an artwork into backdated, empty git commits."""

import os
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import git
from git.exc import GitCommandError

from .art_repo import Log, default_branch, is_tool_checkout, open_art_repo, push_branch
from .artwork import DAYS_PER_WEEK, MAX_WEEKS, Grid, count_commits, validate_grid
from .dates import get_first_sunday_of_year, pixel_timestamp
from .github import commit_email_warning, fetch_is_fork, github_slug

PROGRESS_EVERY = 10
"""Log a progress line every this many commits."""

ART_MESSAGE_PREFIX = "pixel art "
"""Start of every art commit message, which is also how earlier art is recognised."""

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
    dry_run: bool = False,
    log: Log = print,
) -> int:
    """Create the backdated commits that draw ``grid`` and return how many were made.

    ``target_repo`` is the art repository: a local path, or a URL that is cloned
    into the working directory. The start is ``start_date`` or, if that is None,
    the first Sunday of ``year`` plus ``offset_weeks`` (at most ``MAX_WEEKS``;
    negative values reach into the previous year). Each pixel is committed
    ``level * multiplier`` times at 12:00 UTC on its day.

    The commits are empty: they reuse the tip's tree, so no file, the index or
    the working tree changes. Art commits already on the branch (recognised by
    ``ART_MESSAGE_PREFIX`` and their UTC day) count towards each pixel, so
    re-running a drawing adds nothing and a higher multiplier adds only the
    difference. ``dry_run`` runs every check and reports that plan without
    committing.

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

    if dry_run:
        rev = art_branch if art_branch and art_branch in repo.heads else "HEAD"
        plan = _plan(repo, rev, grid, start_date, multiplier)
        log(
            f"Dry run: would create {plan.new_commits} commits on '{branch}' "
            f"({plan.present} already present). No commits were made."
        )
        return plan.new_commits

    original_ref = _current_ref(repo) if art_branch else None
    stashed = False
    try:
        if art_branch:
            stashed = _stash_changes(repo, art_branch, log)
            _switch_to_branch(repo, art_branch, log)
        _ensure_clean(repo, force)
        plan = _plan(repo, "HEAD", grid, start_date, multiplier)
        log(f"{plan.new_commits} commits to create, {plan.present} already present.")
        total = _commit_artwork(repo, branch, plan, log)
        if total:
            log(f"Created {total} backdated commits on branch {branch}.")
        else:
            log(f"Nothing new: the art is already on branch {branch}.")
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
            "your profile and would fill the tool's history with fake commits. Use a "
            "repository you own instead, e.g. your profile README repository "
            "https://github.com/<username>/<username>."
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
            "forks. Use a repository you own, e.g. your profile README repository."
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


@dataclass(frozen=True)
class _Pixel:
    day: int
    week: int
    when: datetime
    wanted: int
    present: int


@dataclass(frozen=True)
class _Plan:
    pixels: list[_Pixel]

    @property
    def present(self) -> int:
        return sum(min(pixel.present, pixel.wanted) for pixel in self.pixels)

    @property
    def new_commits(self) -> int:
        return sum(max(0, pixel.wanted - pixel.present) for pixel in self.pixels)


def _plan(repo: git.Repo, rev: str, grid: Grid, start_date: datetime, multiplier: int) -> _Plan:
    """Pair every lit pixel with the art commits ``rev`` already has on its day."""
    present = _art_commits_per_day(repo, rev)
    pixels = []
    for week in range(len(grid[0])):
        for day in range(DAYS_PER_WEEK):
            if wanted := grid[day][week] * multiplier:
                when = pixel_timestamp(start_date, week, day)
                pixels.append(_Pixel(day, week, when, wanted, present[when.date()]))
    return _Plan(pixels)


def _art_commits_per_day(repo: git.Repo, rev: str) -> Counter[date]:
    """Count the art commits reachable from ``rev`` by UTC day (none on an unborn branch)."""
    if not repo.head.is_valid() and rev == "HEAD":
        return Counter()
    log = repo.git.log("--format=%at %s", rev)
    days: Counter[date] = Counter()
    for line in log.splitlines():
        timestamp, _, subject = line.partition(" ")
        if subject.startswith(ART_MESSAGE_PREFIX):
            days[datetime.fromtimestamp(int(timestamp), UTC).date()] += 1
    return days


def _commit_artwork(repo: git.Repo, branch: str, plan: _Plan, log: Log) -> int:
    """Create the commits ``plan`` still needs on top of HEAD; return how many.

    ``branch`` only moves once every commit exists, so a failure leaves it untouched.
    """
    tip = repo.head.commit.hexsha if repo.head.is_valid() else None
    tree = repo.head.commit.tree.hexsha if tip else _empty_tree(repo)
    total = 0
    for pixel in plan.pixels:
        for index in range(pixel.present + 1, pixel.wanted + 1):
            message = f"{ART_MESSAGE_PREFIX}({pixel.day},{pixel.week}) [{index}/{pixel.wanted}]"
            tip = _commit_pixel(repo, tree, tip, pixel.when, message)
            total += 1
            if total % PROGRESS_EVERY == 0:
                log(f"  ... {total} commits so far")
    if total and tip:
        repo.git.update_ref("-m", "github-pixel-artworks", f"refs/heads/{branch}", tip)
    return total


def _empty_tree(repo: git.Repo) -> str:
    """Write git's empty tree and return its id, for the first commit of an empty repo."""
    return repo.git.hash_object("-t", "tree", "-w", os.devnull)


def _commit_pixel(
    repo: git.Repo, tree: str, parent: str | None, when: datetime, message: str
) -> str:
    """Create one empty commit of ``tree`` on ``parent``, dated ``when``; return its id.

    ``git commit-tree`` never reads the index, so staged work stays out of the art,
    and it runs no hooks. ``when`` is timezone-aware, so git never applies the
    local timezone.
    """
    stamp = when.isoformat()
    env = {**os.environ, "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
    parents = ["-p", parent] if parent else []
    return repo.git.commit_tree(tree, *parents, "-m", message, env=env)
