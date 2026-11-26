from datetime import datetime
from pathlib import Path

import pytest

from github_pixel_artworks.cli import cli, perform_pixel_art


def test_perform_pixel_art_dry_run(capsys):
    grid = [[1, 0], [0, 1], [0, 0], [0, 0], [0, 0], [0, 0], [0, 0]]
    start = datetime(2026, 1, 4)
    perform_pixel_art(
        target_repo=".",
        grid=grid,
        start_date=start,
        multiplier=2,
        dry_run=True,
    )
    out = capsys.readouterr().out
    assert "GitHub Pixel Art Preview" in out
    assert "Dry run complete" in out
    assert "Total commits that will be created: 4" in out


def test_perform_pixel_art_empty_grid(capsys):
    perform_pixel_art(
        target_repo=".", grid=[[], [], [], [], [], [], []], start_date=datetime(2026, 1, 4)
    )
    assert "Nothing to do" in capsys.readouterr().out


def test_cli_help(monkeypatch):
    monkeypatch.setattr("sys.argv", ["github-pixel-artworks", "--help"])
    with pytest.raises(SystemExit) as exc:
        cli()
    assert exc.value.code == 0


def _run_cli(monkeypatch, *argv: str) -> dict:
    """Run the CLI with apply_drawing stubbed out and return the kwargs it received."""
    captured: dict = {}

    def fake_apply(**kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr("github_pixel_artworks.cli.apply_drawing", fake_apply)
    monkeypatch.setattr("sys.argv", ["github-pixel-artworks", *argv])
    cli()
    return captured


SIMPLE = str(Path(__file__).resolve().parents[1] / "data" / "simple.txt")


def test_cli_passes_orphan_branch_name(monkeypatch):
    kwargs = _run_cli(monkeypatch, "-i", SIMPLE, "--year", "2026", "--branch", "my-art", "-y")
    assert kwargs["branch"] == "my-art"
    assert kwargs["in_place"] is False


@pytest.mark.parametrize("alias", ["current", "HEAD", "in-place"])
def test_cli_branch_aliases_mean_in_place(monkeypatch, alias):
    kwargs = _run_cli(monkeypatch, "-i", SIMPLE, "--year", "2026", "--branch", alias, "-y")
    assert kwargs["in_place"] is True


def test_cli_expands_bare_artworks_branch_with_year(monkeypatch):
    kwargs = _run_cli(monkeypatch, "-i", SIMPLE, "--year", "2026", "--art-branch", "artworks", "-y")
    assert kwargs["art_branch"] == "artworks-2026"


@pytest.mark.parametrize("value", ["0", "-2"])
def test_cli_rejects_non_positive_multiplier(monkeypatch, value):
    with pytest.raises(SystemExit) as exc:
        _run_cli(monkeypatch, "-i", SIMPLE, "--year", "2026", "--multiplier", value, "-y")
    assert exc.value.code == 5


def test_cli_requires_a_start(monkeypatch):
    with pytest.raises(SystemExit) as exc:
        _run_cli(monkeypatch, "-i", SIMPLE)
    assert exc.value.code == 2
