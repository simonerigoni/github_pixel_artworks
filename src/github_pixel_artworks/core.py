"""
Core logic for github-pixel-artworks.

Contains grid handling, date calculations for GitHub contribution positioning,
preview, and the main apply_drawing function used by both CLI and GUI.
"""

import os
import shutil
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import git
from git.exc import GitCommandError, InvalidGitRepositoryError

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
    path = p

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

    stripped = [line.rstrip("\r\n") for line in lines if line.strip() or True]

    art_lines = [ln for ln in stripped if ln]
    if len(art_lines) != 7 and len(stripped) != 7:
        if len([item for item in stripped if item or True]) < 7:
            raise ValueError(
                f"Artwork must have exactly 7 rows (days of week). Got {len(art_lines)} non-empty lines in {path}"
            )

    rows = stripped[:7]
    if len(rows) != 7:
        rows = (rows + [""] * 7)[:7]

    width = len(rows[0]) if rows else 0
    if width == 0:
        raise ValueError("Artwork has zero width.")
    if width > MAX_WEEKS:
        raise ValueError(
            f"Artwork must have at most {MAX_WEEKS} weeks (columns). Got {width} in {path}"
        )

    grid: list[list[int]] = []
    for row in rows:
        if len(row) != width:
            if len(row) < width:
                row = row + " " * (width - len(row))
            else:
                row = row[:width]
        prow: list[int] = []
        for c in row:
            cl = c.lower()
            if cl in (" ", ".", "x", "0"):
                v = 0
            elif cl in ("*", "1"):
                v = 1
            elif c.isdigit():
                v = min(int(c), 9)
            elif cl in ("#", "h"):
                v = 4
            else:
                v = 0
            prow.append(v)
        grid.append(prow)

    if len(grid) != 7 or any(len(r) != width for r in grid):
        raise ValueError("Failed to produce a clean 7xN grid.")
    return grid


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


# ---------------------------------------------------------------------------
# Date helpers (auto-align inspired by gelstudios/gitfiti)
# ---------------------------------------------------------------------------


def get_auto_start_date(offset_weeks: int = 0) -> datetime:
    """
    Return a datetime for the Sunday that starts the ~1-year-ago window,
    shifted by `offset_weeks`.

    This positions art on the left side of the contribution graph the user
    currently sees on their profile (plus offset).
    """
    today = datetime.now().date()
    start = datetime(today.year - 1, today.month, today.day, 12, 0, 0)
    while start.weekday() < 6:
        start += timedelta(days=1)
    start += timedelta(weeks=offset_weeks)
    return start


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


def fetch_max_daily_commits(username: str) -> int | None:
    """
    Fetch the public contributions calendar for a username and return the
    highest number of contributions recorded on any single day.

    Uses only stdlib (no extra network deps). Only public data is visible.
    """
    url = f"https://github.com/users/{username}/contributions"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        print(f"Warning: failed to fetch GitHub contributions for '{username}': {e}")
        return None

    maxc = 0
    for line in html.splitlines():
        if "data-date=" not in line or "contributions" not in line.lower():
            continue
        try:
            text = line.split(">", 1)[1].split("<", 1)[0].strip()
            num = text.split()[0]
            if num.isdigit():
                maxc = max(maxc, int(num))
        except Exception:
            continue
    return maxc or None


def calculate_multiplier(max_commits: int) -> int:
    """Scale so that a level-4 cell in our grid becomes roughly the darkest square the user already has."""
    if max_commits <= 0:
        return 1
    m = max_commits / 4.0
    return max(1, int(m + 0.999))


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
# Core non-interactive apply logic (used by both CLI and the new GUI)
# ---------------------------------------------------------------------------


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
    log: Callable[[str], None] = print,
) -> int:
    """Non-interactive core that creates the backdated commits for a drawing.

    - If year is given, start_date is computed as first Sunday of the year + offset_weeks.
      offset_weeks is limited to 0..MAX_WEEKS (negative values are tolerated for
      CLI flexibility when targeting the prior year).
    - Otherwise start_date must be provided (offset_weeks is ignored in that path
      but still validated for sanity).
    - in_place=True (the mode used for *this* dedicated art repo) adds commits directly
      on the current branch using --allow-empty.
    - If art_branch is provided (e.g. "artworks-2025" or "artworks-2016"), the function will:
        * If dirty: auto-stash changes
        * checkout -B <art_branch>
        * perform the art commits on that branch
        * after, pop the stash (your source changes come back)
      This is the recommended way to keep clean history separation.
    - offset_weeks: limited to <= MAX_WEEKS (52). See validation in the function body.
    - log() receives all progress / messages.
    - Returns the number of commits created.
    - Raises on fatal errors (dirty repo without force, bad repo, etc.).
    """
    width = len(grid[0]) if grid else 0
    if width == 0:
        log("Nothing to do (empty grid).")
        return 0

    if offset_weeks > MAX_WEEKS:
        raise ValueError(f"offset_weeks must not exceed {MAX_WEEKS} (got {offset_weeks}).")

    # Resolve start date
    if start_date is None:
        if year is None:
            raise ValueError("Either year or start_date must be provided to apply_drawing")
        start_date = get_first_sunday_of_year(year) + timedelta(weeks=offset_weeks)

    if isinstance(start_date, datetime):
        pass
    else:
        start_date = datetime.combine(start_date, datetime.min.time())

    log("=== GitHub Pixel Art ===")
    log(preview(grid, start_date, multiplier))
    log("")

    # Open repo
    try:
        repo = git.Repo(target_repo)
    except InvalidGitRepositoryError:
        raise RuntimeError(f"{target_repo} is not a git repository") from None

    stashed = False
    effective_in_place = in_place
    if art_branch:
        log(f"Preparing dedicated art branch '{art_branch}'...")
        if repo.is_dirty(untracked_files=True):
            log("Working tree dirty — auto-stashing changes...")
            repo.git.stash("push", "-m", f"auto-stash before art on {art_branch}")
            stashed = True
        repo.git.checkout("-B", art_branch)
        log(f"Now on branch '{art_branch}' (clean for generation).")
        effective_in_place = True

    if repo.is_dirty(untracked_files=True) and not force:
        raise RuntimeError(
            "Target repo has uncommitted changes or untracked files. "
            "Commit/stash them or use force=True."
        )

    if effective_in_place:
        log("In-place mode: backdated art commits will be added directly to the current branch.")
        log("This is the intended mode for a repository whose sole purpose is pixel artworks.")
        active = repo.active_branch.name if not repo.head.is_detached else "DETACHED"
        log(f"Will commit on current HEAD ({active}).")
    else:
        branch_name = "pixel-art"
        log(f"Creating orphan branch '{branch_name}' for a clean art-only history...")
        repo.git.checkout("--orphan", branch_name)
        try:
            repo.git.rm("-r", "--cached", ".")
        except GitCommandError:
            pass
        root = Path(target_repo).resolve()
        for item in list(root.iterdir()):
            if item.name == ".git":
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink(missing_ok=True)

        readme = root / "README.md"
        readme.write_text(
            f"# GitHub Pixel Art\n\n"
            f"Generated on {datetime.now().isoformat()} using github-pixel-artworks\n"
            f"Repo: https://github.com/simonerigoni/github_pixel_artworks\n\n"
            f"Branch: {branch_name}\n",
            encoding="utf-8",
        )
        repo.index.add(["README.md"])
        repo.index.commit("chore: initialize pixel-art branch")
        log("Orphan branch initialized with clean working tree.")

    # Emit the art commits
    log("\nCreating backdated commits...")
    total = 0
    for w in range(width):
        for h in range(7):
            level = grid[h][w] * multiplier
            if level <= 0:
                continue
            base = start_date + timedelta(weeks=w, days=h)
            for k in range(level):
                cdate = base.replace(tzinfo=UTC)
                date_str = cdate.strftime("%Y-%m-%dT%H:%M:%S")
                env = os.environ.copy()
                env["GIT_AUTHOR_DATE"] = date_str
                env["GIT_COMMITTER_DATE"] = date_str
                msg = f"pixel art ({h},{w}) [{k + 1}/{level}]"
                repo.git.commit("--allow-empty", "-m", msg, env=env)
                total += 1
                if total % 10 == 0:
                    log(f"  ... {total} commits so far")

    final_branch = repo.active_branch.name if not repo.head.is_detached else "unknown"
    log(f"\nDone! Created {total} backdated commits on branch {final_branch}.")

    if stashed:
        try:
            repo.git.stash("pop")
            log("Restored stashed source changes.")
        except Exception as se:
            log(f"Warning: could not pop stash: {se}")

    return total
