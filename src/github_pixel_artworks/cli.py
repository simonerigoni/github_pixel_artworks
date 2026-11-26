"""Command line interface: ``github-pixel-artworks``."""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import NoReturn

from . import __version__
from .artwork import MAX_WEEKS, Grid, load_grid
from .dates import MAX_YEAR, MIN_YEAR, SUNDAY, get_auto_start_date, get_first_sunday_of_year
from .github import calculate_multiplier, fetch_max_daily_commits
from .painter import DEFAULT_ORPHAN_BRANCH, apply_drawing, preview

EXIT_DRAWING_FAILED = 2
EXIT_BAD_ARTWORK = 4
EXIT_BAD_ARGUMENT = 5

IN_PLACE_BRANCH_ALIASES = ("", "current", "HEAD", "in-place")
"""``--branch`` values that mean the same as ``--in-place``."""

YEAR_BRANCH_PLACEHOLDERS = ("artworks", "art", "dedicated-art")
"""``--art-branch`` values expanded to ``artworks-<year>`` when ``--year`` is given."""


def perform_pixel_art(
    target_repo: str,
    grid: Grid,
    start_date: datetime,
    multiplier: int = 1,
    branch: str = DEFAULT_ORPHAN_BRANCH,
    dry_run: bool = False,
    yes: bool = False,
    force: bool = False,
    in_place: bool = False,
    art_branch: str | None = None,
    username: str | None = None,
) -> None:
    """Preview the artwork, ask for confirmation unless ``yes``, then draw it.

    ``branch`` is the orphan branch name, ignored with ``in_place`` or
    ``art_branch``. ``username`` is only used for the orphan branch README link
    when the repo has no GitHub remote. Exits with ``EXIT_DRAWING_FAILED`` if
    drawing fails.
    """
    if not grid or not grid[0]:
        print("Nothing to do (empty grid).")
        return

    print("=== GitHub Pixel Art Preview ===")
    print(preview(grid, start_date, multiplier))
    print()
    if dry_run:
        print("Dry run complete. No commits were made.")
        return

    in_place = in_place or branch in IN_PLACE_BRANCH_ALIASES
    print(_mode_description(in_place, art_branch, branch))
    if not yes and not _confirm():
        print("Aborted by user.")
        return

    try:
        apply_drawing(
            grid=grid,
            start_date=start_date,
            target_repo=target_repo,
            multiplier=multiplier,
            in_place=in_place,
            force=force,
            art_branch=art_branch,
            username=username,
            branch=branch,
            log=print,
        )
    except Exception as error:  # report any failure as a CLI error
        _fail(str(error), EXIT_DRAWING_FAILED)


def _mode_description(in_place: bool, art_branch: str | None, branch: str) -> str:
    if art_branch:
        return (
            f"Art commits will be added to branch '{art_branch}'. "
            "Your current branch and uncommitted changes are restored afterwards."
        )
    if in_place:
        return "Art commits will be added to the current branch."
    return (
        f"Warning: this creates backdated commits on a new orphan branch '{branch}'. "
        "Use it only in a repository dedicated to pixel art."
    )


def _confirm() -> bool:
    answer = input("Type 'yes' to continue (or anything else to abort): ")
    return answer.strip().lower() == "yes"


def _fail(message: str, exit_code: int) -> NoReturn:
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(exit_code)


def _print_stderr(message: str) -> None:
    print(message, file=sys.stderr)


def _warn(message: str) -> None:
    _print_stderr(f"Warning: {message}")


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for the ``github-pixel-artworks`` command."""
    parser = argparse.ArgumentParser(
        prog="github-pixel-artworks",
        description="Draw pixel art on your GitHub contribution graph with backdated commits.",
        epilog="Tip: keep each year's art on its own branch with --art-branch artworks-YYYY.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "-i",
        "--input",
        "--artwork",
        dest="input",
        required=True,
        type=Path,
        help="Artwork file: 7 lines (Sunday to Saturday), one character per week.",
    )

    start = parser.add_argument_group("where the art starts (one is required)")
    start.add_argument("--year", type=int, help="Start on the first Sunday of this year.")
    start.add_argument("--start-date", help="Start on this date, YYYY-MM-DD (should be a Sunday).")
    start.add_argument(
        "--auto-align",
        action="store_true",
        help="Start on the first Sunday of the profile's visible year (today - 365 days).",
    )
    parser.add_argument(
        "--offset-weeks",
        type=int,
        default=0,
        help=f"Shift the art right by this many weeks (at most {MAX_WEEKS}). "
        "Used with --year and --auto-align.",
    )

    parser.add_argument(
        "--username",
        help="GitHub username: scale intensity so level 4 matches your darkest existing day.",
    )
    parser.add_argument(
        "--multiplier",
        type=int,
        default=1,
        help="Commits per level, applied on top of --username scaling (default: 1).",
    )

    target = parser.add_argument_group("where the commits go")
    target.add_argument(
        "--target-repo",
        default=".",
        help="Git repository that receives the commits (default: current directory).",
    )
    target.add_argument(
        "--art-branch",
        "--dedicated-branch",
        dest="art_branch",
        help="Commit on this branch (created if missing), then return to your branch and "
        "restore uncommitted changes. With --year, 'artworks' becomes 'artworks-<year>'.",
    )
    target.add_argument("--in-place", action="store_true", help="Commit on the current branch.")
    target.add_argument(
        "--branch",
        default=DEFAULT_ORPHAN_BRANCH,
        help=f"Orphan branch to create otherwise (default: {DEFAULT_ORPHAN_BRANCH}). "
        "'current', 'HEAD' and 'in-place' mean --in-place.",
    )

    parser.add_argument(
        "--dry-run", action="store_true", help="Show the preview without committing."
    )
    parser.add_argument("-y", "--yes", action="store_true", help="Do not ask for confirmation.")
    parser.add_argument(
        "--force", action="store_true", help="Allow a dirty working tree (not recommended)."
    )
    return parser


def _resolve_start_date(args: argparse.Namespace, parser: argparse.ArgumentParser) -> datetime:
    if args.start_date:
        try:
            return datetime.strptime(args.start_date, "%Y-%m-%d")
        except ValueError:
            _fail("--start-date must be in YYYY-MM-DD format.", EXIT_BAD_ARGUMENT)
    if args.year is not None:
        if not MIN_YEAR <= args.year <= MAX_YEAR:
            _fail(f"--year must be between {MIN_YEAR} and {MAX_YEAR}.", EXIT_BAD_ARGUMENT)
        return get_first_sunday_of_year(args.year) + timedelta(weeks=args.offset_weeks)
    if args.auto_align:
        return get_auto_start_date(args.offset_weeks)
    parser.error("one of --start-date, --year or --auto-align is required.")


def _resolve_art_branch(args: argparse.Namespace) -> str | None:
    """Expand a bare ``--art-branch artworks`` to ``artworks-<year>`` when ``--year`` is given."""
    art_branch = args.art_branch
    if art_branch and args.year is not None:
        if art_branch.strip().lower() in YEAR_BRANCH_PLACEHOLDERS:
            art_branch = f"artworks-{args.year}"
            print(f"Using art branch '{art_branch}' (from --year {args.year}).")
    return art_branch


def _resolve_multiplier(args: argparse.Namespace) -> int:
    if not args.username:
        return args.multiplier
    max_daily = fetch_max_daily_commits(args.username, log=_print_stderr)
    if max_daily is None:
        return args.multiplier
    auto_multiplier = calculate_multiplier(max_daily)
    print(f"Profile '{args.username}' has at most {max_daily} contributions on one day.")
    print(f"Auto-computed multiplier: {auto_multiplier}")
    return args.multiplier * auto_multiplier


def cli() -> None:
    """Entry point of the ``github-pixel-artworks`` command."""
    parser = build_parser()
    args = parser.parse_args()

    try:
        grid = load_grid(args.input)
    except (OSError, ValueError) as error:
        _fail(f"could not load artwork: {error}", EXIT_BAD_ARTWORK)
    if args.multiplier < 1:
        _fail("--multiplier must be at least 1.", EXIT_BAD_ARGUMENT)
    if args.offset_weeks > MAX_WEEKS:
        _fail(f"--offset-weeks must not exceed {MAX_WEEKS}.", EXIT_BAD_ARGUMENT)

    start = _resolve_start_date(args, parser)
    art_branch = _resolve_art_branch(args)
    if start.weekday() != SUNDAY:
        _warn(f"{start.date()} is not a Sunday, so columns won't line up with GitHub's weeks.")
    multiplier = _resolve_multiplier(args)

    perform_pixel_art(
        target_repo=args.target_repo,
        grid=grid,
        start_date=start,
        multiplier=multiplier,
        branch=args.branch,
        dry_run=args.dry_run,
        yes=args.yes,
        force=args.force,
        in_place=args.in_place,
        art_branch=art_branch,
        username=args.username,
    )


if __name__ == "__main__":
    cli()
