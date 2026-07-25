#!/usr/bin/env python
"""
github-pixel-artworks CLI

Command line interface for creating pixel artworks in GitHub contributions.
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

from . import __version__
from .core import (
    MAX_WEEKS,
    apply_drawing,
    calculate_multiplier,
    fetch_max_daily_commits,
    get_auto_start_date,
    get_first_sunday_of_year,
    load_grid,
    preview,
)


def perform_pixel_art(
    target_repo: str,
    grid: list[list[int]],
    start_date: datetime,
    multiplier: int = 1,
    branch: str = "pixel-art",
    dry_run: bool = False,
    yes: bool = False,
    force: bool = False,
    in_place: bool = False,
    art_branch: str | None = None,
    username: str | None = None,
) -> None:
    """CLI-facing wrapper. Keeps the classic interactive banners + yes prompts,
    but delegates the actual repo/commit work to the reusable apply_drawing().
    art_branch is passed through for dedicated branch support.
    The recommended convention is to use year-specific names (artworks-YYYY).
    username is only used as a fallback owner when generating an orphan-branch README.
    """
    width = len(grid[0]) if grid else 0
    if width == 0:
        print("Nothing to do (empty grid).")
        return

    print("=== GitHub Pixel Art Preview ===")
    print(preview(grid, start_date, multiplier))
    print()

    if dry_run:
        print("Dry run complete. No commits were made.")
        return

    effective_in_place = in_place or branch in ("", "current", "HEAD", "in-place")

    if effective_in_place and in_place:
        print(
            "\nIn-place mode: backdated art commits will be added directly to the current branch.\n"
            "GitHub will show contribution squares on the chosen dates.\n"
            "This is the intended and expected behavior for a repository whose sole purpose\n"
            "is to host pixel artworks (as you have indicated for this repo).\n"
        )
    else:
        WARNING = (
            "\n"
            "!!! WARNING !!!\n"
            "This will create backdated commits in the target repository.\n"
            "GitHub will show contribution squares on those dates.\n"
            "Use ONLY on dedicated repositories or on a fresh orphan branch.\n"
            "Running this on your main history can make `git log` confusing.\n"
        )
        print(WARNING)

    if not yes:
        resp = input("Type 'yes' to continue (or anything else to abort): ").strip().lower()
        if resp != "yes":
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
            log=print,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)


def cli() -> None:
    parser = argparse.ArgumentParser(
        prog="github-pixel-artworks",
        description="Draw pixel art on your GitHub contributions graph using backdated commits.",
        epilog=(
            "Use --art-branch artworks-YYYY (e.g. --art-branch artworks-2025) (or --in-place) "
            "when this repository's only purpose is to host pixel artworks. "
            "The recommended convention is a year-specific branch so each year's art is isolated. "
            "--art-branch will auto-manage stashing and branch creation for clean separation.\n"
            "See the README for details and examples."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    parser.add_argument(
        "-i",
        "--input",
        "--artwork",
        dest="input",
        required=True,
        type=Path,
        help="Path to a 7-line text file describing the artwork (rows=days, cols=weeks). "
        "Legacy x/* format from temp/contributionartwork/artwork is supported.",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        help="Explicit start date as YYYY-MM-DD (should be a Sunday for correct week alignment).",
    )
    parser.add_argument(
        "--auto-align",
        action="store_true",
        help="Automatically choose a start date ~1 year ago (first Sunday on/after today-365d) + offset.",
    )
    parser.add_argument(
        "--offset-weeks",
        type=int,
        default=0,
        help=f"Shift the art this many weeks to the right (0..{MAX_WEEKS}). "
        "Works with --year (weeks after first Sunday of the year) or --auto-align.",
    )
    parser.add_argument(
        "--year",
        type=int,
        help="Target calendar year (e.g. 2025). The tool will automatically start the art on the first Sunday of that year. "
        "Use --offset-weeks to move it right within the year. This is the simplest way to position art for a specific year.",
    )
    parser.add_argument(
        "--username",
        help="GitHub username. If given, the tool will fetch your public contribution calendar "
        "and compute a multiplier so that level-4 pixels match (or exceed) your current darkest square.",
    )
    parser.add_argument(
        "--multiplier",
        type=int,
        default=1,
        help="Manual intensity multiplier (applied on top of any --username scaling).",
    )
    parser.add_argument(
        "--target-repo",
        default=".",
        help="Path to the git repository that will receive the commits (default: current directory).",
    )
    parser.add_argument(
        "--branch",
        default="pixel-art",
        help="Name of the orphan branch to create (default: pixel-art). "
        "Use --in-place instead when this repository's *only* purpose is pixel artworks.",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Commit the pixel artworks directly onto the current branch (instead of creating a separate orphan branch). "
        "This is the recommended and intended mode when using *this* repository itself as your dedicated pixel art canvas.",
    )
    parser.add_argument(
        "--art-branch",
        "--dedicated-branch",
        dest="art_branch",
        default=None,
        help="Create or switch to a dedicated branch for the artwork commits (e.g. 'artworks-2025' or 'artworks-2016'). "
        "Highly recommended to include the target year in the name. "
        "If the working tree is dirty, changes will be auto-stashed, "
        "the branch created/switched, art commits created on it, then stash popped. "
        "This avoids dirty-repo errors and keeps source development history separate from art commits. "
        "If you pass the bare name 'artworks' together with --year, it will be automatically turned into 'artworks-<year>'.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse everything, print the plan and preview, but make no changes.",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip the interactive confirmation prompt.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow running even if the target repo is dirty (not recommended).",
    )

    args = parser.parse_args()

    try:
        grid = load_grid(args.input)
    except Exception as e:
        print(f"Error loading artwork: {e}", file=sys.stderr)
        sys.exit(4)

    if args.offset_weeks > MAX_WEEKS:
        print(
            f"Error: --offset-weeks must not exceed {MAX_WEEKS}.",
            file=sys.stderr,
        )
        sys.exit(5)

    if args.start_date:
        try:
            start = datetime.strptime(args.start_date, "%Y-%m-%d")
        except ValueError:
            print("Error: --start-date must be in YYYY-MM-DD format.", file=sys.stderr)
            sys.exit(5)
    elif args.year is not None:
        if args.year < 2000 or args.year > 2100:
            print("Error: --year must be a reasonable value (e.g. 2015-2030).", file=sys.stderr)
            sys.exit(5)
        start = get_first_sunday_of_year(args.year)
        start += timedelta(weeks=args.offset_weeks)
    elif args.auto_align:
        start = get_auto_start_date(args.offset_weeks)
    else:
        parser.error(
            "You must supply one of: --start-date, --year, or --auto-align (--offset-weeks works with --year and --auto-align)."
        )

    # Auto-apply user's preferred year-specific branch naming convention.
    # If someone passes the bare "--art-branch artworks" (or similar) together with --year,
    # turn it into "artworks-YYYY" automatically.
    if args.art_branch:
        ab = args.art_branch.strip()
        if ab.lower() in ("artworks", "art", "dedicated-art"):
            if args.year is not None:
                args.art_branch = f"artworks-{args.year}"
                print(
                    f"Info: using year-specific art branch '{args.art_branch}' (from --year {args.year})"
                )
            # If no explicit year (e.g. only --start-date or --auto-align), leave it as-is or default to "artworks"

    if start.weekday() != 6:
        print(
            f"WARNING: {start.date()} is not a Sunday (weekday={start.weekday()}). "
            "The columns may not line up with GitHub week boundaries.",
            file=sys.stderr,
        )

    mult = args.multiplier
    if args.username:
        maxc = fetch_max_daily_commits(args.username)
        if maxc is not None:
            auto_m = calculate_multiplier(maxc)
            print(
                f"Profile for '{args.username}' shows a max of {maxc} contributions on a single day."
            )
            print(f"Auto-computed multiplier: {auto_m}")
            mult = args.multiplier * auto_m

    perform_pixel_art(
        target_repo=args.target_repo,
        grid=grid,
        start_date=start,
        multiplier=mult,
        branch=args.branch,
        dry_run=args.dry_run,
        yes=args.yes,
        force=args.force,
        in_place=args.in_place,
        art_branch=args.art_branch,
        username=args.username,
    )


if __name__ == "__main__":
    cli()
