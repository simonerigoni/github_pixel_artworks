"""Generated artwork patterns."""

import pytest

from github_pixel_artworks.artwork import validate_grid
from github_pixel_artworks.config import (
    DAYS_PER_WEEK,
    MAX_WEEKS,
    PATTERN_FONT_GAP,
    PATTERN_FONT_WIDTH,
    PATTERN_MIRROR,
    PATTERN_NAMES,
    PATTERN_OVERFLOW_TRUNCATE,
    PATTERN_RANDOM,
    PATTERN_TETRIS,
    PATTERN_TEXT,
    PATTERN_WAVE,
    TETROMINOES,
    TOP_LEVEL,
)
from github_pixel_artworks.patterns import GENERATORS, generate, text_width


def assert_valid(grid: list[list[int]], width: int | None = None) -> None:
    validate_grid(grid)
    assert len(grid) == DAYS_PER_WEEK
    if width is not None:
        assert len(grid[0]) == width
    for row in grid:
        for level in row:
            assert 0 <= level <= TOP_LEVEL


class TestRegistry:
    def test_every_named_pattern_has_a_generator(self) -> None:
        assert tuple(GENERATORS) == PATTERN_NAMES

    def test_rejects_an_unknown_name(self) -> None:
        with pytest.raises(ValueError, match="Unknown pattern"):
            generate("paisley")


class TestShapeAndSeed:
    @pytest.mark.parametrize("name", [PATTERN_RANDOM, PATTERN_MIRROR, PATTERN_WAVE, PATTERN_TETRIS])
    def test_a_seeded_pattern_is_deterministic_and_in_range(self, name: str) -> None:
        first = generate(name, width=16, seed=42)
        second = generate(name, width=16, seed=42)
        other = generate(name, width=16, seed=43)

        assert_valid(first, 16)
        assert first == second
        assert first != other

    def test_rejects_a_width_outside_the_year(self) -> None:
        with pytest.raises(ValueError, match="width"):
            generate(PATTERN_RANDOM, width=0, seed=1)
        with pytest.raises(ValueError, match="width"):
            generate(PATTERN_RANDOM, width=MAX_WEEKS + 1, seed=1)

    def test_rejects_a_density_outside_zero_to_one(self) -> None:
        with pytest.raises(ValueError, match="density"):
            generate(PATTERN_RANDOM, width=8, seed=1, density=1.5)


class TestMirror:
    def test_is_symmetric_left_to_right(self) -> None:
        for width in (15, 16):
            grid = generate(PATTERN_MIRROR, width=width, seed=7)
            assert_valid(grid, width)
            for row in grid:
                assert row == row[::-1]


class TestWave:
    def test_uses_more_than_one_shade(self) -> None:
        grid = generate(PATTERN_WAVE, width=20, seed=1)
        levels = {level for row in grid for level in row}
        assert 0 in levels
        assert len(levels) >= 3


class TestTetris:
    def test_filled_cells_come_in_tetrominoes(self) -> None:
        grid = generate(PATTERN_TETRIS, width=20, seed=11)
        assert_valid(grid, 20)
        filled = sum(1 for row in grid for level in row if level)
        assert filled > 0
        assert filled % 4 == 0

    def test_every_rotation_is_four_distinct_cells(self) -> None:
        for piece in TETROMINOES:
            for cells in piece:
                assert len(cells) == 4
                assert len(set(cells)) == 4

    def test_the_first_piece_rests_on_saturday(self) -> None:
        from random import Random

        from github_pixel_artworks.patterns import _blank, _drop_piece

        grid = _blank(10)
        assert _drop_piece(grid, Random(0))
        assert any(grid[-1])  # gravity is toward the last row (Saturday)


class TestText:
    def test_simone_fits_and_is_centred(self) -> None:
        grid = generate(PATTERN_TEXT, text="Simone", width=41)
        assert_valid(grid, 41)
        needed = text_width("SIMONE")
        assert needed == 6 * PATTERN_FONT_WIDTH + 5 * PATTERN_FONT_GAP
        origin = (41 - needed) // 2
        # The 'S' glyph has its top-left pixel off and the next two on (0b01110).
        assert grid[0][origin : origin + 5] == [0, 4, 4, 4, 0]
        # Padding on both sides is empty.
        assert all(row[origin - 1] == 0 for row in grid)
        assert all(row[origin + needed] == 0 for row in grid)

    def test_left_align_starts_at_the_first_column(self) -> None:
        grid = generate(PATTERN_TEXT, text="HI", width=20, align="left")
        assert grid[0][:5] == [4, 0, 0, 0, 4]  # H, top row 10001
        assert all(row[-1] == 0 for row in grid)

    def test_too_long_text_raises(self) -> None:
        with pytest.raises(ValueError, match="needs"):
            generate(PATTERN_TEXT, text="SIMONEOKX", overflow="error")

    def test_truncate_keeps_whole_characters(self) -> None:
        # 9 letters need 53 weeks; 8 letters need 47, which fits in 52.
        grid = generate(
            PATTERN_TEXT, text="SIMONEOKX", overflow=PATTERN_OVERFLOW_TRUNCATE, width=MAX_WEEKS
        )
        assert_valid(grid, MAX_WEEKS)
        assert text_width("SIMONEOK") == 47
        # The last kept glyph is K, not a clipped X.
        # 8 letters centred in 52: origin = (52-47)//2 = 2; K starts at 2+7*6 = 44
        origin = (MAX_WEEKS - text_width("SIMONEOK")) // 2
        k_at = origin + 7 * (PATTERN_FONT_WIDTH + PATTERN_FONT_GAP)
        assert grid[3][k_at : k_at + 5] == [4, 4, 0, 0, 0]  # K's middle row is 11000

    def test_rejects_an_unsupported_character(self) -> None:
        with pytest.raises(ValueError, match="Unsupported character"):
            generate(PATTERN_TEXT, text="HI@YOU")

    def test_rejects_empty_text(self) -> None:
        with pytest.raises(ValueError, match="needs some text"):
            generate(PATTERN_TEXT, text="   ")

    def test_text_width_of_an_empty_string_is_zero(self) -> None:
        assert text_width("  ") == 0
