"""The github-pixel-artworks command, with apply_drawing stubbed out where it would commit."""

from datetime import datetime
from pathlib import Path

import git
import pytest

from github_pixel_artworks.artwork import count_commits, load_grid
from github_pixel_artworks.cli import cli, perform_pixel_art
from github_pixel_artworks.config import EXIT_BAD_ARGUMENT, EXIT_BAD_ARTWORK, EXIT_DRAWING_FAILED
from github_pixel_artworks.patterns import generate

SIMPLE = str(Path(__file__).resolve().parents[1] / "data" / "simple.txt")
TWO_PIXELS = [[1, 0], [0, 1], [0, 0], [0, 0], [0, 0], [0, 0], [0, 0]]
ART_REPO = "https://github.com/you/pixel-art"


@pytest.fixture
def run_cli(monkeypatch: pytest.MonkeyPatch):
    """Run the CLI with ``argv``; return the keyword arguments apply_drawing received."""

    def run(*argv: str) -> dict:
        received: dict = {}

        def fake_apply_drawing(**kwargs: object) -> int:
            received.update(kwargs)
            return 0

        monkeypatch.setattr("github_pixel_artworks.cli.apply_drawing", fake_apply_drawing)
        monkeypatch.setattr("sys.argv", ["github-pixel-artworks", *argv])
        cli()
        return received

    return run


def exit_code_of(run, *argv: str) -> int | str | None:
    with pytest.raises(SystemExit) as raised:
        run(*argv)
    return raised.value.code


class TestPerformPixelArt:
    def test_dry_run_prints_the_preview_without_committing(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        perform_pixel_art(
            target_repo=None,
            grid=TWO_PIXELS,
            start_date=datetime(2026, 1, 4),
            multiplier=2,
            dry_run=True,
        )

        out = capsys.readouterr().out
        assert "GitHub Pixel Art Preview" in out
        assert "Total commits that will be created: 4" in out
        assert "Dry run complete" in out

    def test_empty_grid_does_nothing(self, capsys: pytest.CaptureFixture[str]) -> None:
        perform_pixel_art(target_repo=".", grid=[[]] * 7, start_date=datetime(2026, 1, 4))

        assert "Nothing to do" in capsys.readouterr().out

    def test_answering_no_aborts(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr("builtins.input", lambda _prompt: "no")

        perform_pixel_art(target_repo=".", grid=TWO_PIXELS, start_date=datetime(2026, 1, 4))

        assert "Aborted by user." in capsys.readouterr().out

    def test_drawing_failure_exits_with_an_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as raised:
            perform_pixel_art(
                target_repo=str(tmp_path),
                grid=TWO_PIXELS,
                start_date=datetime(2026, 1, 4),
                yes=True,
            )

        assert raised.value.code == EXIT_DRAWING_FAILED
        assert "Error: " in capsys.readouterr().err


class TestArguments:
    def test_help_exits_successfully(self, run_cli) -> None:
        assert exit_code_of(run_cli, "--help") == 0

    def test_a_start_is_required(self, run_cli) -> None:
        assert exit_code_of(run_cli, "-i", SIMPLE) == 2  # argparse usage error

    def test_year_starts_on_its_first_sunday_plus_offset(self, run_cli) -> None:
        received = run_cli(
            "-i", SIMPLE, "--year", "2026", "--offset-weeks", "2", "-t", ART_REPO, "-y"
        )

        assert received["start_date"] == datetime(2026, 1, 18)

    def test_the_art_repository_and_push_are_passed_through(self, run_cli) -> None:
        received = run_cli("-i", SIMPLE, "--year", "2026", "-t", ART_REPO, "--push", "-y")

        assert received["target_repo"] == ART_REPO
        assert received["push"] is True
        assert received["art_branch"] is None

    def test_keep_clone_is_passed_through(self, run_cli) -> None:
        received = run_cli("-i", SIMPLE, "--year", "2026", "-t", ART_REPO, "--keep-clone", "-y")

        assert received["keep_clone"] is True

    def test_the_clone_is_cleaned_up_by_default(self, run_cli) -> None:
        received = run_cli("-i", SIMPLE, "--year", "2026", "-t", ART_REPO, "-y")

        assert received["keep_clone"] is False

    def test_the_art_repository_is_required(
        self, run_cli, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert exit_code_of(run_cli, "-i", SIMPLE, "--year", "2026", "-y") == EXIT_BAD_ARGUMENT
        assert "--target-repo" in capsys.readouterr().err

    def test_the_target_defaults_to_the_detected_profile_repository(
        self, run_cli, set_global_git_config, capsys: pytest.CaptureFixture[str]
    ) -> None:
        set_global_git_config("github.user", "octocat")

        received = run_cli("-i", SIMPLE, "--year", "2026", "-y")

        assert received["target_repo"] == "https://github.com/octocat/octocat"
        assert received["username"] == "octocat"
        captured = capsys.readouterr()
        assert "git config github.user" in captured.out
        assert "could not fetch" not in captured.err  # no auto-scaling network call

    def test_an_explicit_username_picks_the_profile_repository(self, run_cli) -> None:
        received = run_cli("-i", SIMPLE, "--year", "2026", "--username", "someone", "-y")

        assert received["target_repo"] == "https://github.com/someone/someone"

    def test_dry_run_with_an_art_repository_checks_it_without_committing(self, run_cli) -> None:
        received = run_cli("-i", SIMPLE, "--year", "2026", "-t", ART_REPO, "--dry-run")

        assert received["dry_run"] is True
        assert received["target_repo"] == ART_REPO

    def test_dry_run_needs_no_art_repository(
        self, run_cli, capsys: pytest.CaptureFixture[str]
    ) -> None:
        run_cli("-i", SIMPLE, "--year", "2026", "--dry-run")

        assert "Dry run complete" in capsys.readouterr().out

    def test_bare_artworks_branch_gets_the_year(self, run_cli) -> None:
        received = run_cli(
            "-i", SIMPLE, "--year", "2026", "--art-branch", "artworks", "-t", ".", "-y"
        )

        assert received["art_branch"] == "artworks-2026"

    @pytest.mark.parametrize(
        "argv",
        [
            ("--year", "2026", "--multiplier", "0"),
            ("--year", "2026", "--offset-weeks", "53"),
            ("--year", "1999"),
            ("--start-date", "2026/01/04"),
        ],
    )
    def test_invalid_values_exit_with_bad_argument(self, run_cli, argv: tuple[str, ...]) -> None:
        assert exit_code_of(run_cli, "-i", SIMPLE, *argv, "-t", ART_REPO, "-y") == EXIT_BAD_ARGUMENT

    def test_unreadable_artwork_exits_with_bad_artwork(self, run_cli, tmp_path: Path) -> None:
        missing = str(tmp_path / "missing.txt")

        assert exit_code_of(run_cli, "-i", missing, "--year", "2026") == EXIT_BAD_ARTWORK

    def test_non_sunday_start_warns(self, run_cli, capsys: pytest.CaptureFixture[str]) -> None:
        run_cli("-i", SIMPLE, "--start-date", "2026-01-05", "-t", ART_REPO, "-y")

        assert "Warning: 2026-01-05 is not a Sunday" in capsys.readouterr().err


class TestPatternArguments:
    def test_a_pattern_is_an_alternative_to_an_artwork_file(self, run_cli) -> None:
        received = run_cli(
            "--pattern", "tetris", "--seed", "4", "--year", "2026", "-t", ART_REPO, "-y"
        )

        assert received["grid"] == generate("tetris", seed=4)
        assert received["dry_run"] is False

    def test_dry_run_previews_a_pattern(self, run_cli, capsys: pytest.CaptureFixture[str]) -> None:
        run_cli("--pattern", "text", "--pattern-text", "HI", "--year", "2026", "--dry-run")

        out = capsys.readouterr().out
        assert "GitHub Pixel Art Preview" in out
        assert "Dry run complete" in out

    def test_dry_run_with_a_target_uses_the_generated_grid(self, run_cli) -> None:
        received = run_cli(
            "--pattern", "wave", "--seed", "2", "--year", "2026", "-t", ART_REPO, "--dry-run"
        )

        assert received["dry_run"] is True
        assert received["grid"] == generate("wave", seed=2)

    def test_pattern_and_input_cannot_both_be_given(self, run_cli) -> None:
        assert exit_code_of(run_cli, "-i", SIMPLE, "--pattern", "random", "--year", "2026") == 2

    def test_text_pattern_needs_pattern_text(self, run_cli) -> None:
        assert (
            exit_code_of(run_cli, "--pattern", "text", "--year", "2026", "--dry-run")
            == EXIT_BAD_ARGUMENT
        )

    def test_a_source_is_required(self, run_cli) -> None:
        assert exit_code_of(run_cli, "--year", "2026", "--dry-run") == 2


def test_cli_draws_into_a_real_repo(git_repo: git.Repo, monkeypatch: pytest.MonkeyPatch) -> None:
    root = str(git_repo.working_tree_dir)
    monkeypatch.setattr(
        "sys.argv",
        [
            "github-pixel-artworks",
            "-i",
            SIMPLE,
            "--year",
            "2026",
            "-y",
            "--target-repo",
            root,
        ],
    )

    cli()

    assert len(list(git_repo.iter_commits())) == 1 + count_commits(load_grid(SIMPLE))
