"""Artwork file format, intensity levels and drawing paths."""

from pathlib import Path

import pytest

from github_pixel_artworks.artwork import (
    count_commits,
    drawing_path,
    grid_to_text,
    level_color,
    load_grid,
    save_grid,
    validate_grid,
)
from github_pixel_artworks.config import EMPTY_COLOR, LEVEL_COLORS, MAX_WEEKS

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def write_artwork(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "art.txt"
    path.write_text(text, encoding="utf-8")
    return path


class TestLoadGrid:
    def test_reads_every_supported_character(self, tmp_path: Path) -> None:
        path = write_artwork(tmp_path, " .xX0*123456789#hH?\n" * 7)

        grid = load_grid(path)

        assert grid[0] == [0, 0, 0, 0, 0, 1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 4, 4, 4, 0]

    def test_accepts_the_widest_example(self) -> None:
        grid = load_grid(DATA_DIR / "space_invaders.txt")

        assert len(grid) == 7
        assert all(len(row) == MAX_WEEKS for row in grid)

    def test_accepts_narrow_artwork(self, tmp_path: Path) -> None:
        path = write_artwork(tmp_path, "*\n" * 7)

        assert load_grid(path) == [[1]] * 7

    def test_takes_width_from_the_widest_row(self, tmp_path: Path) -> None:
        # Editors that strip trailing whitespace turn an empty top row into "".
        path = write_artwork(tmp_path, "\n  * *\n *****\n *****\n  ***\n   *\n\n")

        grid = load_grid(path)

        assert all(len(row) == 6 for row in grid)
        assert grid[0] == [0] * 6
        assert grid[1] == [0, 0, 1, 0, 1, 0]

    def test_ignores_trailing_blank_lines(self, tmp_path: Path) -> None:
        path = write_artwork(tmp_path, "*\n" * 7 + "\n\n")

        assert len(load_grid(path)) == 7

    def test_treats_non_ascii_digits_as_empty(self, tmp_path: Path) -> None:
        path = write_artwork(tmp_path, "\u00b2*\n" * 7)  # superscript two

        assert load_grid(path)[0] == [0, 1]

    @pytest.mark.parametrize("rows", [6, 8])
    def test_rejects_wrong_row_count(self, tmp_path: Path, rows: int) -> None:
        path = write_artwork(tmp_path, "*\n" * rows)

        with pytest.raises(ValueError, match="7 rows"):
            load_grid(path)

    def test_rejects_artwork_wider_than_a_year(self, tmp_path: Path) -> None:
        path = write_artwork(tmp_path, ("*" * (MAX_WEEKS + 1) + "\n") * 7)

        with pytest.raises(ValueError, match=str(MAX_WEEKS)):
            load_grid(path)

    def test_rejects_zero_width(self, tmp_path: Path) -> None:
        path = write_artwork(tmp_path, "\n" * 7)

        with pytest.raises(ValueError, match="zero width"):
            load_grid(path)

    def test_missing_file_raises_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_grid(tmp_path / "missing.txt")


class TestSaveGrid:
    def test_writes_level_one_as_star_and_higher_levels_as_digits(self) -> None:
        grid = [[0, 1, 2, 9, 12]] * 7

        text = grid_to_text(grid)

        assert text.splitlines()[0] == " *299"
        assert text.endswith("\n")

    def test_round_trips_every_level(self, tmp_path: Path) -> None:
        grid = [[(row + column) % 10 for column in range(10)] for row in range(7)]
        path = tmp_path / "nested" / "levels.txt"

        save_grid(path, grid)

        assert load_grid(path) == grid

    @pytest.mark.parametrize("example", sorted(DATA_DIR.glob("*.txt")), ids=lambda p: p.name)
    def test_round_trips_the_shipped_examples(self, tmp_path: Path, example: Path) -> None:
        grid = load_grid(example)
        path = tmp_path / example.name

        save_grid(path, grid)

        assert load_grid(path) == grid


class TestDrawingPath:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [("my_art", "my_art.txt"), (" heart.txt ", "heart.txt"), ("", "untitled.txt")],
    )
    def test_builds_a_txt_path_inside_the_data_dir(
        self, tmp_path: Path, name: str, expected: str
    ) -> None:
        assert drawing_path(tmp_path, name) == tmp_path / expected

    @pytest.mark.parametrize("name", ["../evil", "sub/dir", "..", "C:\\temp\\x", "/etc/passwd"])
    def test_rejects_names_that_leave_the_data_dir(self, tmp_path: Path, name: str) -> None:
        with pytest.raises(ValueError, match="Invalid drawing name"):
            drawing_path(tmp_path, name)


class TestGridHelpers:
    def test_validate_grid_rejects_ragged_rows(self) -> None:
        grid = [[1, 0]] * 6 + [[1]]

        with pytest.raises(ValueError, match="same width"):
            validate_grid(grid)

    def test_validate_grid_rejects_wrong_row_count(self) -> None:
        with pytest.raises(ValueError, match="7"):
            validate_grid([[1]] * 6)

    def test_count_commits_applies_the_multiplier(self) -> None:
        grid = [[1, 0], [0, 2], [0, 0], [0, 0], [0, 0], [0, 0], [0, 0]]

        assert count_commits(grid, multiplier=3) == 9

    @pytest.mark.parametrize(
        ("level", "color"),
        [(0, EMPTY_COLOR), (1, LEVEL_COLORS[1]), (4, LEVEL_COLORS[4]), (9, LEVEL_COLORS[4])],
    )
    def test_level_color_uses_the_darkest_green_above_level_four(
        self, level: int, color: str
    ) -> None:
        assert level_color(level) == color
