"""
Core logic for github-pixel-artworks.

Contains grid handling, date calculations for GitHub contribution positioning,
preview, and the main apply_drawing function used by both CLI and GUI.
"""

import math
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import git
from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError

# ---------------------------------------------------------------------------
# Limits (GitHub contribution graphs show ~52 weeks per year view)
# ---------------------------------------------------------------------------

MAX_WEEKS: int = 52


# ---------------------------------------------------------------------------
# Grid loading / saving (supports the legacy temp/ example format + modern digits)
# ---------------------------------------------------------------------------


def load_grid(path: Path | str) -> list[list[int]]:
    """
    Load a 7-row artwork grid.

    Each line = one row (top row = Sunday for week 0).
    Each character position in the line = one week column.
    Width (number of weeks/columns) must be 1..MAX_WEEKS (52).

    Supported chars (case-insensitive where sensible):
        empty: ' ', '.', 'x', 'X', '0'
        level 1: '*', '1'
        level 2: '2'
        level 3: '3'
        level 4+: '4', '#', 'H', 'h' (higher values also accepted as digits)

    The legacy temp/contributionartwork/artwork file works out of the box
    (x = 0, * = 1).
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Artwork file not found: {path}")

    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    # Trailing blank lines are just file formatting; blank lines *inside* the
    # first 7 are real (empty) rows, e.g. when an editor strips trailing spaces.
    while len(lines) > 7 and not lines[-1].strip():
        lines.pop()
    if len(lines) != 7:
        raise ValueError(
            f"Artwork must have exactly 7 rows (days of week). Got {len(lines)} in {p}"
        )

    width = max(len(row) for row in lines)
    if width == 0:
        raise ValueError(f"Artwork has zero width: {p}")
    if width > MAX_WEEKS:
        raise ValueError(
            f"Artwork must have at most {MAX_WEEKS} weeks (columns). Got {width} in {p}"
        )

    return [[_cell_level(c) for c in row.ljust(width)] for row in lines]


def _cell_level(char: str) -> int:
    """Map one artwork character to its intensity level (unknown characters are empty)."""
    if char in "123456789":
        return int(char)
    if char == "*":
        return 1
    if char.lower() in ("#", "h"):
        return 4
    return 0


def grid_to_text(grid: list[list[int]]) -> str:
    """Convert internal grid (0/1+) back to a simple text representation using
    ' ' for empty and '*' for filled (compatible with load_grid and legacy files).
    Higher levels are collapsed to '*' for the basic editor case.
    """
    lines = []
    for row in grid:
        line = "".join("*" if cell > 0 else " " for cell in row)
        lines.append(line)
    return "\n".join(lines) + "\n"


def save_grid(path: Path | str, grid: list[list[int]]) -> None:
    """Save a grid to a 7-line .txt file.
    Creates parent directories if needed.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = grid_to_text(grid)
    p.write_text(text, encoding="utf-8")


def drawing_path(data_dir: Path | str, name: str) -> Path:
    """Return ``data_dir/<name>.txt`` for a user-typed drawing name.

    Empty names become ``untitled``. Names containing path separators or ``..``
    are rejected with ValueError so a drawing can never be written (or deleted)
    outside ``data_dir``.
    """
    stem = name.strip() or "untitled"
    if stem.endswith(".txt"):
        stem = stem[: -len(".txt")]
    if not stem or stem in (".", "..") or any(sep in stem for sep in ("/", "\\", ":")):
        raise ValueError(f"Invalid drawing name: {name!r} (use a plain file name)")
    return Path(data_dir) / f"{stem}.txt"


# ---------------------------------------------------------------------------
# Date helpers (auto-align inspired by gelstudios/gitfiti)
# ---------------------------------------------------------------------------


def get_auto_start_date(offset_weeks: int = 0, today: date | None = None) -> datetime:
    """
    Return a datetime for the Sunday that starts the ~1-year-ago window,
    shifted by `offset_weeks`.

    The window starts on the first Sunday on/after ``today - 365 days``, which
    positions art on the left side of the contribution graph the user currently
    sees on their profile (plus offset). ``today`` defaults to the local date.
    """
    base = (today or date.today()) - timedelta(days=365)
    base += timedelta(days=(6 - base.weekday()) % 7)
    return datetime(base.year, base.month, base.day) + timedelta(weeks=offset_weeks)


def get_first_sunday_of_year(year: int) -> datetime:
    """
    Return a datetime for the first Sunday of the given year (Jan 1 or the
    following Sunday).

    This is the natural left edge for contribution art targeting that calendar
    year. Combine with offset_weeks to shift the drawing right within the year.
    """
    jan1 = datetime(year, 1, 1)
    days_until_sunday = (6 - jan1.weekday()) % 7
    return jan1 + timedelta(days=days_until_sunday)


# GitHub usernames: 1-39 alphanumerics or single hyphens, not starting/ending with a hyphen.
_GITHUB_USERNAME_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}")
# Day tooltips look like "12 contributions on May 2nd." / "1 contribution on ..." / "No ...".
_CONTRIBUTIONS_RE = re.compile(r">\s*([\d,]+) contributions? on ")


def is_valid_github_username(username: str) -> bool:
    """Return True if ``username`` is syntactically a valid GitHub login."""
    return _GITHUB_USERNAME_RE.fullmatch(username) is not None


def fetch_max_daily_commits(username: str, log: Callable[[str], None] = print) -> int | None:
    """
    Fetch the public contributions calendar for a username and return the
    highest number of contributions recorded on any single day.

    Uses only stdlib (no extra network deps). Only public data is visible.
    Returns None (after logging a warning) when the username is invalid, the
    page can't be fetched, or no contribution counts are found.
    """
    if not is_valid_github_username(username):
        log(f"Warning: '{username}' is not a valid GitHub username; skipping auto-scaling.")
        return None

    url = f"https://github.com/users/{urllib.parse.quote(username)}/contributions"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError) as e:
        log(f"Warning: failed to fetch GitHub contributions for '{username}': {e}")
        return None

    counts = [int(m.replace(",", "")) for m in _CONTRIBUTIONS_RE.findall(html)]
    return max(counts, default=0) or None


def calculate_multiplier(max_commits: int) -> int:
    """Scale so that a level-4 cell in our grid becomes roughly the darkest square the user already has."""
    if max_commits <= 0:
        return 1
    return max(1, math.ceil(max_commits / 4))


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


def preview(grid: list[list[int]], start_date: datetime, multiplier: int) -> str:
    """Return a small ASCII preview of the artwork (█ = will have >=1 commit)."""
    lines = []
    width = len(grid[0]) if grid else 0
    for h in range(7):
        row = ""
        for w in range(width):
            lvl = grid[h][w] * multiplier
            row += "█" if lvl > 0 else "·"
        lines.append(row)
    end_date = start_date + timedelta(weeks=width - 1, days=6)
    lines.append(f"\nSpan: {start_date.date()} (Sun)  →  {end_date.date()} (Sat)")
    lines.append(f"Total weeks: {width}   |   Multiplier: {multiplier}")
    total = sum(sum(row) for row in grid) * multiplier
    lines.append(f"Total commits that will be created: {total}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# GitHub URL helpers
# ---------------------------------------------------------------------------


def normalize_github_https_url(remote_url: str) -> str | None:
    """Convert a git remote URL into an https://github.com/owner/repo form if possible."""
    raw = remote_url.strip()
    if raw.endswith(".git"):
        raw = raw[:-4]

    if raw.startswith("git@github.com:"):
        path = raw.removeprefix("git@github.com:")
        return f"https://github.com/{path}"

    if raw.startswith("ssh://git@github.com/"):
        path = raw.removeprefix("ssh://git@github.com/")
        return f"https://github.com/{path}"

    if raw.startswith("https://github.com/") or raw.startswith("http://github.com/"):
        # Normalize http -> https and strip trailing slash
        path = raw.split("github.com/", 1)[1].strip("/")
        return f"https://github.com/{path}"

    return None


def resolve_github_repo_url(
    repo: git.Repo,
    username: str | None = None,
    fallback_repo_name: str = "github_pixel_artworks",
) -> str | None:
    """
    Best-effort GitHub HTTPS URL for the target repository.

    Preference order:
    1. ``origin`` remote (or the first available remote)
    2. ``https://github.com/{username}/{fallback_repo_name}`` when username is known
    """
    # ``origin`` first, then any other remote.
    remotes = sorted(repo.remotes, key=lambda r: r.name != "origin")
    candidates: list[str] = []
    for remote in remotes:
        try:
            url = remote.url
        except GitCommandError:  # remote without a URL
            continue
        if url and url not in candidates:
            candidates.append(url)

    for candidate in candidates:
        normalized = normalize_github_https_url(candidate)
        if normalized:
            return normalized

    if username:
        return f"https://github.com/{username}/{fallback_repo_name}"
    return None


# ---------------------------------------------------------------------------
# Core non-interactive apply logic (used by both CLI and the new GUI)
# ---------------------------------------------------------------------------


def _commit_pixel(repo: git.Repo, when: datetime, message: str) -> None:
    """Create one empty commit authored and committed at ``when`` (aware datetime)."""
    stamp = when.isoformat()  # includes the UTC offset, so git never guesses a timezone
    env = {**os.environ, "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
    repo.git.commit("--allow-empty", "--no-verify", "-m", message, env=env)


def _validate_branch_name(repo: git.Repo, name: str) -> None:
    """Raise ValueError unless ``name`` is a valid, non-option-like git branch name."""
    try:
        if name.startswith("-"):
            raise GitCommandError("check-ref-format", 1)
        repo.git.check_ref_format("--branch", name)
    except GitCommandError:
        raise ValueError(f"Invalid branch name: {name!r}") from None


def _current_ref(repo: git.Repo) -> str:
    """Branch name to return to later, or the commit SHA when HEAD is detached."""
    return repo.head.commit.hexsha if repo.head.is_detached else repo.active_branch.name


def _start_orphan_branch(
    repo: git.Repo, branch_name: str, username: str | None, log: Callable[[str], None]
) -> None:
    """Switch to a new orphan branch whose only tracked file is a small README.

    Tracked files of the previous branch leave the working tree (they stay safe in
    that branch's history); untracked and ignored files are left untouched.
    """
    if branch_name in repo.heads:
        raise RuntimeError(
            f"Branch '{branch_name}' already exists. Pick another branch name "
            "or use art_branch to add commits to an existing art branch."
        )
    log(f"Creating orphan branch '{branch_name}' for a clean art-only history...")
    repo.git.checkout("--orphan", branch_name)
    if repo.git.ls_files():
        repo.git.rm("-r", "-f", "--quiet", ".")

    root = Path(str(repo.working_tree_dir))
    repo_url = resolve_github_repo_url(repo, username=username)
    repo_line = f"Repo: {repo_url}\n" if repo_url else ""
    (root / "README.md").write_text(
        f"# GitHub Pixel Art\n\n"
        f"Generated on {datetime.now().isoformat()} using github-pixel-artworks\n"
        f"{repo_line}"
        f"Branch: {branch_name}\n",
        encoding="utf-8",
    )
    repo.index.add(["README.md"])
    repo.index.commit("chore: initialize pixel-art branch")
    log("Orphan branch initialized with clean working tree.")


def _emit_art_commits(
    repo: git.Repo,
    grid: list[list[int]],
    start_date: datetime,
    multiplier: int,
    log: Callable[[str], None],
) -> int:
    """Create the backdated commits for every pixel; returns how many were made."""
    # Pin every pixel to noon UTC on its day: GitHub buckets contributions by UTC
    # date, so a local-midnight timestamp could land on the previous day.
    first_day = start_date.date()
    total = 0
    for w in range(len(grid[0])):
        for h in range(7):
            level = grid[h][w] * multiplier
            day = first_day + timedelta(weeks=w, days=h)
            when = datetime(day.year, day.month, day.day, 12, tzinfo=UTC)
            for k in range(level):
                _commit_pixel(repo, when, f"pixel art ({h},{w}) [{k + 1}/{level}]")
                total += 1
                if total % 10 == 0:
                    log(f"  ... {total} commits so far")
    return total


def apply_drawing(
    grid: list[list[int]],
    year: int | None = None,
    start_date: datetime | None = None,
    offset_weeks: int = 0,
    target_repo: str = ".",
    multiplier: int = 1,
    in_place: bool = True,
    force: bool = False,
    art_branch: str | None = None,
    username: str | None = None,
    branch: str = "pixel-art",
    log: Callable[[str], None] = print,
) -> int:
    """Non-interactive core that creates the backdated commits for a drawing.

    - If year is given, start_date is computed as first Sunday of the year + offset_weeks.
      offset_weeks is limited to <= MAX_WEEKS (negative values are tolerated for
      CLI flexibility when targeting the prior year).
    - Otherwise start_date must be provided (offset_weeks is ignored in that path
      but still validated for sanity). Only its calendar date is used: each pixel is
      committed at 12:00 UTC on its day so GitHub shows it on the intended square.
    - multiplier must be >= 1; each cell's level is multiplied by it.
    - in_place=True (the mode used for *this* dedicated art repo) adds commits directly
      on the current branch using --allow-empty.
    - in_place=False creates the orphan branch ``branch`` (default "pixel-art") whose
      only file is a small README; it fails if that branch already exists.
    - If art_branch is provided (e.g. "artworks-2025" or "artworks-2016"), the function will:
        * If dirty: auto-stash changes (including untracked files)
        * switch to <art_branch>, creating it from HEAD if it does not exist yet
          (an existing art branch is reused, so earlier art is kept)
        * perform the art commits on that branch
        * switch back to the original branch and pop the stash, even on failure
      This is the recommended way to keep clean history separation.
    - username: optional GitHub owner used only as a fallback when writing the orphan-branch
      README link (prefer the repo remote URL when available).
    - log() receives all progress / messages.
    - Returns the number of commits created.
    - Raises on fatal errors (ValueError for bad input, RuntimeError for repo problems).
    """
    width = len(grid[0]) if grid else 0
    if width == 0:
        log("Nothing to do (empty grid).")
        return 0
    if len(grid) != 7 or any(len(row) != width for row in grid):
        raise ValueError("grid must have exactly 7 rows of equal width")
    if multiplier < 1:
        raise ValueError(f"multiplier must be at least 1 (got {multiplier}).")
    if offset_weeks > MAX_WEEKS:
        raise ValueError(f"offset_weeks must not exceed {MAX_WEEKS} (got {offset_weeks}).")

    if start_date is None:
        if year is None:
            raise ValueError("Either year or start_date must be provided to apply_drawing")
        start_date = get_first_sunday_of_year(year) + timedelta(weeks=offset_weeks)

    log("=== GitHub Pixel Art ===")
    log(preview(grid, start_date, multiplier))
    log("")

    try:
        repo = git.Repo(target_repo)
    except InvalidGitRepositoryError, NoSuchPathError:
        raise RuntimeError(f"{target_repo} is not a git repository") from None

    if art_branch:
        _validate_branch_name(repo, art_branch)
    elif not in_place:
        _validate_branch_name(repo, branch)

    original_ref = _current_ref(repo)
    stashed = False
    try:
        if art_branch:
            log(f"Preparing dedicated art branch '{art_branch}'...")
            if repo.is_dirty(untracked_files=True):
                log("Working tree dirty — auto-stashing changes...")
                repo.git.stash(
                    "push", "--include-untracked", "-m", f"auto-stash before art on {art_branch}"
                )
                stashed = True
            if art_branch in repo.heads:
                repo.git.checkout(art_branch)
            else:
                repo.git.checkout("-b", art_branch)
            log(f"Now on branch '{art_branch}' (clean for generation).")

        if repo.is_dirty(untracked_files=True) and not force:
            raise RuntimeError(
                "Target repo has uncommitted changes or untracked files. "
                "Commit/stash them or use force=True."
            )

        if art_branch or in_place:
            log(
                "In-place mode: backdated art commits will be added directly to the current branch."
            )
            active = repo.active_branch.name if not repo.head.is_detached else "DETACHED"
            log(f"Will commit on current HEAD ({active}).")
        else:
            _start_orphan_branch(repo, branch, username, log)

        log("\nCreating backdated commits...")
        total = _emit_art_commits(repo, grid, start_date, multiplier, log)
        final_branch = repo.active_branch.name if not repo.head.is_detached else "unknown"
        log(f"\nDone! Created {total} backdated commits on branch {final_branch}.")
    finally:
        if art_branch and _current_ref(repo) != original_ref:
            try:
                repo.git.checkout(original_ref)
                log(f"Switched back to '{original_ref}'.")
            except GitCommandError as e:
                log(f"Warning: could not switch back to '{original_ref}': {e}")
        if stashed:
            try:
                repo.git.stash("pop")
                log("Restored stashed source changes.")
            except GitCommandError as e:
                log(f"Warning: could not pop stash (run `git stash pop` manually): {e}")

    return total
