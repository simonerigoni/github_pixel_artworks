"""
Tests for the new MAX_WEEKS limits (artwork width and offset_weeks).

These are the first real (non-dummy) tests exercising validation added for the
"limit the number of weeks to 52" requirement.
"""

import tempfile
from pathlib import Path

import pytest

from github_pixel_artworks import MAX_WEEKS
from github_pixel_artworks.core import load_grid, apply_drawing


def test_max_weeks_constant():
    assert MAX_WEEKS == 52
    # Also re-exported at package level for discoverability
    from github_pixel_artworks import MAX_WEEKS as MAX2

    assert MAX2 == 52


def test_load_grid_rejects_more_than_52_weeks():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "too_wide.txt"
        # 53 columns (one more than allowed), 7 rows
        content = ("*" * (MAX_WEEKS + 1) + "\n") * 7
        p.write_text(content, encoding="utf-8")
        with pytest.raises(ValueError, match=str(MAX_WEEKS)):
            load_grid(p)


def test_load_grid_accepts_exactly_52_weeks_via_real_data():
    # space_invaders.txt is the canonical 52-week example
    p = Path("data/space_invaders.txt")
    assert p.exists(), "expected data file for boundary test"
    grid = load_grid(p)
    assert len(grid) == 7
    assert len(grid[0]) == MAX_WEEKS
    # All rows same width
    assert all(len(row) == MAX_WEEKS for row in grid)


def test_load_grid_accepts_small_widths():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "tiny.txt"
        p.write_text(("*" * 7 + "\n") * 7, encoding="utf-8")
        grid = load_grid(p)
        assert len(grid[0]) == 7


def test_apply_drawing_rejects_offset_greater_than_max():
    grid = [[0] * 5 for _ in range(7)]
    with pytest.raises(ValueError, match=str(MAX_WEEKS)):
        # target_repo="." will never be reached; the offset check is early
        apply_drawing(
            grid=grid,
            year=2025,
            offset_weeks=MAX_WEEKS + 1,
            target_repo=".",
        )


def test_apply_drawing_accepts_offset_exactly_max_and_negative():
    grid = [[0] * 3 for _ in range(7)]
    # offset=52 should pass the new check (later will fail on git repo / dirty etc.)
    try:
        apply_drawing(
            grid=grid,
            year=2025,
            offset_weeks=MAX_WEEKS,
            target_repo=".",  # will raise later (InvalidGitRepository or similar)
        )
    except ValueError as e:
        # We must NOT have hit our offset limit
        assert "offset_weeks" not in str(e).lower()
        assert "exceed" not in str(e).lower()
    except Exception:
        # Any other exception (git, dirty tree, etc.) is fine — validation passed
        pass

    # Negative offset (CLI flexibility) must also not raise the limit error
    try:
        apply_drawing(
            grid=grid,
            year=2025,
            offset_weeks=-3,
            target_repo=".",
        )
    except ValueError as e:
        assert "offset_weeks" not in str(e).lower()
        assert "exceed" not in str(e).lower()
    except Exception:
        pass
