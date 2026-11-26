"""Command line interface: ``github-pixel-artworks``."""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import NoReturn

from . import __version__
from .artwork import Grid, load_grid
from .config import (
    ART_BRANCH_PREFIX,
    EXIT_BAD_ARGUMENT,
    EXIT_BAD_ARTWORK,
    EXIT_DRAWING_FAILED,
    MAX_WEEKS,
    MAX_YEAR,
    MIN_YEAR,
    SUNDAY,
    YEAR_BRANCH_PLACEHOLDERS,
)
from .dates import get_auto_start_date, get_first_sunday_of_year
from .github import (
    calculate_multiplier,
    detect_github_username,
    fetch_max_daily_commits,
    profile_repo_url,
)
from .painter import apply_drawing, preview


def perform_pixel_art(
    target_repo: str | None,
    grid: Grid,
    start_date: datetime,
    multiplier: int = 1,
    dry_run: bool = False,
    yes: bool = False,
    force: bool = False,
    art_branch: str | None = None,
    username: str | None = None,
    push: bool = False,
    keep_clone: bool = False,
) -> None:
    """Preview the artwork, ask for confirmation unless ``yes``, then draw it.

    ``target_repo`` is the art repository (a path or URL). A dry run without one
    only prints the preview; with one it also checks the repository and reports
    how many commits are new. Exits with ``EXIT_BAD_ARGUMENT`` when it is missing and with
    ``EXIT_DRAWING_FAILED`` if drawing fails.
    """
    if not grid or not grid[0]:
        print("Nothing to do (empty grid).")
        return

    print("=== GitHub Pixel Art Preview ===")
    print(preview(grid, start_date, multiplier))
    print()
    if dry_run and not target_repo:
        print("Dry run complete. No commits were made.")
        return
    if not target_repo:
        _fail(
            "--target-repo is required, because no GitHub user was detected: pass the URL "
            "or path of a repository you own, e.g. https://github.com/<username>/<username>, "
            "or set your user once with: git config --global github.user <username>",
            EXIT_BAD_ARGUMENT,
        )

    if not dry_run:
        print(_mode_description(target_repo, art_branch))
        if not yes and not _confirm():
            print("Aborted by user.")
            return

    try:
        apply_drawing(
            grid=grid,
            target_repo=target_repo,
            start_date=start_date,
            multiplier=multiplier,
            art_branch=art_branch,
            username=username,
            push=push,
            keep_clone=keep_clone,
            force=force,
            dry_run=dry_run,
            log=print,
        )
    except Exception as error:  # report any failure as a CLI error
        _fail(str(error), EXIT_DRAWING_FAILED)


def _mode_description(target_repo: str, art_branch: str | None) -> str:
    if art_branch:
        return (
            f"Art commits will be added to branch '{art_branch}' of '{target_repo}'. "
            "Your current branch and uncommitted changes are restored afterwards."
        )
    return f"Art commits will be added to the default branch of '{target_repo}'."


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
        epilog="Quick start: -i ART --year YYYY "
        "--target-repo https://github.com/<username>/<username> --push",
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

    target = parser.add_argument_group("the target repository")
    target.add_argument(
        "-t",
        "--target-repo",
        help="A repository you own, e.g. your profile README repository "
        "https://github.com/<username>/<username>: a GitHub URL (cloned into a temporary folder) or a "
        "local path. Empty commits go on its default branch. Default: the profile README "
        "repository of your GitHub user, from git config github.user, a no-reply "
        "user.email, a login-shaped user.name, GitHub's commit search by user.email, or gh.",
    )
    target.add_argument("--push", action="store_true", help="Push to origin after drawing.")
    target.add_argument(
        "--keep-clone",
        action="store_true",
        help="Keep the temporary clone of a URL target. By default it is deleted once "
        "nothing in it is unpushed, e.g. after --push.",
    )
    target.add_argument(
        "--art-branch",
        "--dedicated-branch",
        dest="art_branch",
        help="Advanced: commit on this branch (created if missing) instead, then return to "
        "your branch. The art shows only once the branch is the default one. "
        "With --year, 'artworks' becomes 'artworks-<year>'.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the preview without committing; with --target-repo, also check the "
        "repository and count the commits that are new.",
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
            art_branch = f"{ART_BRANCH_PREFIX}-{args.year}"
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


def _resolve_profile(args: argparse.Namespace) -> tuple[str | None, str | None]:
    """Return the GitHub username and target repository, filling gaps from local settings.

    ``--username`` and ``--target-repo`` win; a missing target becomes the
    profile README repository. The detected username is only used for the
    target and the email check, never for --username's auto-scaling.
    """
    username, target_repo = args.username, args.target_repo
    if not username and (detected := detect_github_username()):
        username, source = detected
        print(f"GitHub user '{username}' (from {source}).")
    if not target_repo and username:
        target_repo = profile_repo_url(username)
        print(f"Target repository: {target_repo} (your profile README repository).")
    return username, target_repo


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
    username, target_repo = _resolve_profile(args)

    perform_pixel_art(
        target_repo=target_repo,
        grid=grid,
        start_date=start,
        multiplier=multiplier,
        dry_run=args.dry_run,
        yes=args.yes,
        force=args.force,
        art_branch=art_branch,
        username=username,
        push=args.push,
        keep_clone=args.keep_clone,
    )


if __name__ == "__main__":
    cli()
