from datetime import datetime

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
