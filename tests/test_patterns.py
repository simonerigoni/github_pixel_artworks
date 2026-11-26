"""Generated artwork patterns."""

import pytest

from github_pixel_artworks.artwork import validate_grid
from github_pixel_artworks.config import (
    DAYS_PER_WEEK,
    MAX_WEEKS,
    PATTERN_FONT_GAP,
    PATTERN_FONT_WIDTH,
    PATTERN_GAME_OF_LIFE,
    PATTERN_HEART_GAP,
    PATTERN_HEART_SPRITE,
    PATTERN_HEARTS,
    PATTERN_ICON_DUNGEON_SPRITES,
    PATTERN_ICON_GAP,
    PATTERN_ICON_NATURE_SPRITES,
    PATTERN_ICONS_DUNGEON,
    PATTERN_ICONS_NATURE,
    PATTERN_INVADER_SPRITES,
    PATTERN_MIRROR,
    PATTERN_NAMES,
    PATTERN_OVERFLOW_TRUNCATE,
    PATTERN_RANDOM,
    PATTERN_SPACE_INVADERS,
    PATTERN_STRIPES,
    PATTERN_TETRIS,
    PATTERN_TETRIS_DENSITY,
    PATTERN_TETRIS_MAX_HEIGHT,
    PATTERN_TETRIS_MIN_HEIGHT,
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
    @pytest.mark.parametrize(
        "name",
        [
            PATTERN_RANDOM,
            PATTERN_MIRROR,
            PATTERN_WAVE,
            PATTERN_TETRIS,
            PATTERN_SPACE_INVADERS,
            PATTERN_GAME_OF_LIFE,
            PATTERN_HEARTS,
            PATTERN_STRIPES,
            PATTERN_ICONS_DUNGEON,
            PATTERN_ICONS_NATURE,
        ],
    )
    def test_a_seeded_pattern_is_deterministic_and_in_range(self, name: str) -> None:
        first = generate(name, width=16, seed=42)
        second = generate(name, width=16, seed=42)
        other = generate(name, width=16, seed=7)

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

    def test_each_piece_is_one_shade_and_neighbours_differ(self) -> None:
        for seed in (1, 11, 42, 99):
            grid = generate(PATTERN_TETRIS, width=20, seed=seed)
            pieces = _same_shade_groups(grid)
            assert pieces
            for cells, level in pieces:
                assert len(cells) == 4
                assert all(grid[r][c] == level for r, c in cells)
                assert _is_tetromino(cells)
            cells_to_level = {cell: level for cells, level in pieces for cell in cells}
            for (row, column), level in cells_to_level.items():
                for nrow, ncol in ((row - 1, column), (row, column - 1)):
                    neighbour = cells_to_level.get((nrow, ncol))
                    if neighbour is not None and (nrow, ncol) not in _group_of(
                        pieces, (row, column)
                    ):
                        assert neighbour != level

    def test_the_stack_is_not_a_full_board(self) -> None:
        grid = generate(PATTERN_TETRIS, width=20, seed=11)
        cells = DAYS_PER_WEEK * 20
        filled = sum(1 for row in grid for level in row if level)
        assert 0 < filled < cells
        heights = _grounded_heights(grid)
        assert all(height <= PATTERN_TETRIS_MAX_HEIGHT for height in heights)
        assert any(height >= PATTERN_TETRIS_MIN_HEIGHT for height in heights)

    def test_the_skyline_varies_in_height(self) -> None:
        for seed in (1, 11, 42, 99):
            grid = generate(PATTERN_TETRIS, width=20, seed=seed)
            heights = [height for height in _grounded_heights(grid) if height]
            assert heights
            assert max(heights) - min(heights) >= 2
            assert min(heights) >= PATTERN_TETRIS_MIN_HEIGHT
            assert max(heights) <= PATTERN_TETRIS_MAX_HEIGHT

    def test_the_default_board_is_sparse(self) -> None:
        for width in (20, 52):
            for seed in (1, 11, 29, 42, 99):
                grid = generate(PATTERN_TETRIS, width=width, seed=seed)
                pieces = len(_same_shade_groups(grid))
                filled = pieces * 4
                cells = DAYS_PER_WEEK * width
                assert 0 < filled / cells <= 0.28
                # Roughly a piece every three or four weeks, plus a falling one.
                assert 1 <= pieces <= max(6, width // 2)
                if width >= 20:
                    assert _longest_empty_run(_grounded_heights(grid)) >= 2

    def test_a_higher_density_places_more_pieces(self) -> None:
        default = generate(PATTERN_TETRIS, width=52, seed=7)
        sparse = generate(PATTERN_TETRIS, width=52, seed=7, density=PATTERN_TETRIS_DENSITY)
        dense = generate(PATTERN_TETRIS, width=52, seed=7, density=1.0)
        assert default == sparse
        assert len(_same_shade_groups(dense)) > len(_same_shade_groups(sparse))


class TestSpaceInvaders:
    def test_stamps_classic_sprites(self) -> None:
        grid = generate(PATTERN_SPACE_INVADERS, width=52, seed=3)
        assert_valid(grid, 52)
        assert any(level for row in grid for level in row)
        matches = _matching_sprites(grid, PATTERN_INVADER_SPRITES)
        assert matches
        # Each stamped invader uses one or two shades.
        for _origin, on_cells in matches:
            shades = {grid[row][column] for row, column in on_cells}
            assert shades <= set(range(1, TOP_LEVEL + 1))
            assert 1 <= len(shades) <= 2


class TestGameOfLife:
    def test_evolves_a_non_empty_board_with_ages(self) -> None:
        grid = generate(PATTERN_GAME_OF_LIFE, width=52, seed=11)
        assert_valid(grid, 52)
        levels = {level for row in grid for level in row}
        assert 0 in levels
        assert any(level > 0 for level in levels)


class TestHearts:
    def test_repeats_the_five_wide_heart(self) -> None:
        grid = generate(PATTERN_HEARTS, width=52, seed=2)
        assert_valid(grid, 52)
        matches = _matching_sprites(grid, (PATTERN_HEART_SPRITE,))
        assert len(matches) >= 3
        origins = [origin for origin, _cells in matches]
        stride = len(PATTERN_HEART_SPRITE[0]) + PATTERN_HEART_GAP
        assert all(
            right - left == stride for left, right in zip(origins, origins[1:], strict=False)
        )


class TestStripes:
    def test_diagonals_share_a_shade_and_cycle(self) -> None:
        grid = generate(PATTERN_STRIPES, width=20, seed=5)
        assert_valid(grid, 20)
        levels = {level for row in grid for level in row}
        assert levels == {1, 2, 3, 4}
        down_right = all(
            grid[row][column] == grid[row + 1][column + 1]
            for row in range(DAYS_PER_WEEK - 1)
            for column in range(19)
        )
        down_left = all(
            grid[row][column] == grid[row + 1][column - 1]
            for row in range(DAYS_PER_WEEK - 1)
            for column in range(1, 20)
        )
        assert down_right or down_left


class TestIcons:
    @pytest.mark.parametrize(
        "name, sprites",
        [
            (PATTERN_ICONS_DUNGEON, PATTERN_ICON_DUNGEON_SPRITES),
            (PATTERN_ICONS_NATURE, PATTERN_ICON_NATURE_SPRITES),
        ],
    )
    def test_stamps_themed_icons_with_gaps_and_contrasting_shades(
        self, name: str, sprites: tuple[tuple[str, ...], ...]
    ) -> None:
        grid = generate(name, width=52, seed=4)
        assert_valid(grid, 52)
        matches = _matching_sprites(grid, sprites)
        span = len(sprites[0][0])
        assert all(len(sprite[0]) == span for sprite in sprites)
        # 7-wide icons with a 3-column gap fill a 52-week year with five stamps.
        assert len(matches) >= 5
        origins = [origin for origin, _cells in matches]
        assert all(
            right - left == span + PATTERN_ICON_GAP
            for left, right in zip(origins, origins[1:], strict=False)
        )
        assert origins[0] <= PATTERN_ICON_GAP
        assert origins[-1] + span - origins[0] == 5 * span + 4 * PATTERN_ICON_GAP
        shades = [{grid[row][column] for row, column in cells} for _origin, cells in matches]
        for icon_shades in shades:
            assert len(icon_shades) == 1
            assert icon_shades <= set(range(1, TOP_LEVEL + 1))
        consecutive = [next(iter(icon_shades)) for icon_shades in shades]
        assert all(left != right for left, right in zip(consecutive, consecutive[1:], strict=False))
        stamped = [_sprite_at(origin, cells, sprites) for origin, cells in matches]
        assert set(stamped) <= set(sprites)
        assert len(set(stamped)) == min(len(sprites), len(matches))
        assert all(left != right for left, right in zip(stamped, stamped[1:], strict=False))


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


def _same_shade_groups(grid: list[list[int]]) -> list[tuple[set[tuple[int, int]], int]]:
    """Four-connected groups of the same non-zero shade."""
    height, width = len(grid), len(grid[0])
    seen: set[tuple[int, int]] = set()
    groups: list[tuple[set[tuple[int, int]], int]] = []
    for row in range(height):
        for column in range(width):
            if not grid[row][column] or (row, column) in seen:
                continue
            level = grid[row][column]
            stack = [(row, column)]
            cells: set[tuple[int, int]] = set()
            while stack:
                r, c = stack.pop()
                if (r, c) in cells:
                    continue
                cells.add((r, c))
                for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                    if 0 <= nr < height and 0 <= nc < width and grid[nr][nc] == level:
                        stack.append((nr, nc))
            seen.update(cells)
            groups.append((cells, level))
    return groups


def _group_of(
    pieces: list[tuple[set[tuple[int, int]], int]], cell: tuple[int, int]
) -> set[tuple[int, int]]:
    for cells, _level in pieces:
        if cell in cells:
            return cells
    raise AssertionError(f"{cell} is not in any piece")


def _is_tetromino(cells: set[tuple[int, int]]) -> bool:
    min_row = min(row for row, _column in cells)
    min_col = min(column for _row, column in cells)
    shape = tuple(sorted((row - min_row, column - min_col) for row, column in cells))
    return shape in _TETROMINO_SHAPES


def _normalise(cells: tuple[tuple[int, int], ...]) -> tuple[tuple[int, int], ...]:
    min_row = min(row for row, _column in cells)
    min_col = min(column for _row, column in cells)
    return tuple(sorted((row - min_row, column - min_col) for row, column in cells))


_TETROMINO_SHAPES = {_normalise(rotation) for piece in TETROMINOES for rotation in piece}


def _grounded_heights(grid: list[list[int]]) -> list[int]:
    """Skyline height of each column, ignoring a tetromino that is still falling."""
    floating = _floating_cells(grid)
    heights: list[int] = []
    width = len(grid[0])
    for column in range(width):
        filled = [
            row
            for row in range(DAYS_PER_WEEK)
            if grid[row][column] and (row, column) not in floating
        ]
        heights.append(DAYS_PER_WEEK - min(filled) if filled else 0)
    return heights


def _floating_cells(grid: list[list[int]]) -> set[tuple[int, int]]:
    floating: set[tuple[int, int]] = set()
    for cells, _level in _same_shade_groups(grid):
        if any(row == DAYS_PER_WEEK - 1 for row, _column in cells):
            continue
        if any(
            row + 1 < DAYS_PER_WEEK and grid[row + 1][column] and (row + 1, column) not in cells
            for row, column in cells
        ):
            continue
        floating.update(cells)
    return floating


def _longest_empty_run(heights: list[int]) -> int:
    longest = current = 0
    for height in heights:
        if height == 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _sprite_at(
    origin: int,
    cells: set[tuple[int, int]],
    sprites: tuple[tuple[str, ...], ...],
) -> tuple[str, ...]:
    """Return the sprite whose filled cells match ``cells`` at ``origin``."""
    for sprite in sprites:
        top = max(0, (DAYS_PER_WEEK - len(sprite)) // 2)
        mask = {
            (top + drow, origin + dcol)
            for drow, line in enumerate(sprite)
            for dcol, char in enumerate(line)
            if char in "#o"
        }
        if mask == cells:
            return sprite
    raise AssertionError(f"no sprite matched cells at column {origin}")


def _matching_sprites(
    grid: list[list[int]], sprites: tuple[tuple[str, ...], ...]
) -> list[tuple[int, set[tuple[int, int]]]]:
    """Return (origin column, filled cells) for every sprite mask found on the grid."""
    found: list[tuple[int, set[tuple[int, int]]]] = []
    width = len(grid[0])
    for sprite in sprites:
        sprite_width = len(sprite[0])
        top = max(0, (DAYS_PER_WEEK - len(sprite)) // 2)
        mask = [
            (drow, dcol)
            for drow, line in enumerate(sprite)
            for dcol, char in enumerate(line)
            if char in "#o"
        ]
        for origin in range(0, width - sprite_width + 1):
            if all(
                bool(grid[top + drow][origin + dcol]) == ((drow, dcol) in set(mask))
                if 0 <= top + drow < DAYS_PER_WEEK
                else False
                for drow in range(len(sprite))
                for dcol in range(sprite_width)
            ):
                cells = {(top + drow, origin + dcol) for drow, dcol in mask}
                found.append((origin, cells))
    found.sort()
    return found
