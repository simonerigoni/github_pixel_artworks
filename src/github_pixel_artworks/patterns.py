"""Pattern generators: grids the GUI and CLI can draw without a hand-made file."""

from __future__ import annotations

import math
import random
from collections.abc import Callable

from .artwork import Grid, validate_grid
from .config import (
    DAYS_PER_WEEK,
    MAX_WEEKS,
    PATTERN_DEFAULT_DENSITY,
    PATTERN_DEFAULT_WIDTH,
    PATTERN_FONT,
    PATTERN_FONT_GAP,
    PATTERN_FONT_HEIGHT,
    PATTERN_FONT_WIDTH,
    PATTERN_MIRROR,
    PATTERN_NAMES,
    PATTERN_OVERFLOW_ERROR,
    PATTERN_OVERFLOWS,
    PATTERN_RANDOM,
    PATTERN_TETRIS,
    PATTERN_TETRIS_MAX_HEIGHT,
    PATTERN_TETRIS_MIN_HEIGHT,
    PATTERN_TEXT,
    PATTERN_TEXT_ALIGN_CENTER,
    PATTERN_TEXT_ALIGN_LEFT,
    PATTERN_TEXT_ALIGNS,
    PATTERN_WAVE,
    PATTERN_WAVE_PERIOD,
    TETROMINOES,
    TOP_LEVEL,
)

type PatternGenerator = Callable[..., Grid]


def generate(
    name: str,
    *,
    width: int | None = None,
    seed: int | None = None,
    text: str = "",
    align: str = PATTERN_TEXT_ALIGN_CENTER,
    density: float = PATTERN_DEFAULT_DENSITY,
    overflow: str = PATTERN_OVERFLOW_ERROR,
) -> Grid:
    """Return a ``DAYS_PER_WEEK`` by ``width`` grid for the named pattern.

    ``seed`` makes a run reproducible. ``text`` is used only by the text
    pattern; ``align`` is ``center`` or ``left`` within ``width``. If the text
    is wider than ``width`` (or ``MAX_WEEKS`` when width is omitted),
    ``overflow`` is ``error`` or ``truncate`` (whole characters only).

    Raises:
        ValueError: for an unknown name, a bad width, density, align or
            overflow, missing or illegal text, or text that does not fit.
    """
    key = name.strip().lower()
    if key not in GENERATORS:
        raise ValueError(f"Unknown pattern {name!r}. Choose one of: {', '.join(PATTERN_NAMES)}.")
    if not 0 <= density <= 1:
        raise ValueError(f"density must be between 0 and 1 (got {density}).")
    if overflow not in PATTERN_OVERFLOWS:
        raise ValueError(
            f"overflow must be one of: {', '.join(PATTERN_OVERFLOWS)} (got {overflow!r})."
        )
    if align not in PATTERN_TEXT_ALIGNS:
        raise ValueError(f"align must be one of: {', '.join(PATTERN_TEXT_ALIGNS)} (got {align!r}).")
    rng = random.Random(seed)
    columns = PATTERN_DEFAULT_WIDTH if width is None and key != PATTERN_TEXT else width
    if columns is not None:
        columns = _require_width(columns)
    grid = GENERATORS[key](
        width=columns, rng=rng, text=text, align=align, density=density, overflow=overflow
    )
    validate_grid(grid)
    return grid


def text_width(text: str) -> int:
    """Return how many columns ``text`` needs, including gaps, once normalised."""
    characters = _normalise_text(text)
    if not characters:
        return 0
    return len(characters) * PATTERN_FONT_WIDTH + (len(characters) - 1) * PATTERN_FONT_GAP


def _require_width(width: int) -> int:
    if width < 1 or width > MAX_WEEKS:
        raise ValueError(f"pattern width must be between 1 and {MAX_WEEKS} (got {width}).")
    return width


def _blank(width: int) -> Grid:
    return [[0] * width for _ in range(DAYS_PER_WEEK)]


def _random_noise(
    *, width: int | None, rng: random.Random, density: float, **_extra: object
) -> Grid:
    columns = _require_width(width if width is not None else PATTERN_DEFAULT_WIDTH)
    grid = _blank(columns)
    for row in range(DAYS_PER_WEEK):
        for column in range(columns):
            if rng.random() < density:
                grid[row][column] = rng.randint(1, TOP_LEVEL)
    return grid


def _mirror(*, width: int | None, rng: random.Random, density: float, **_extra: object) -> Grid:
    columns = _require_width(width if width is not None else PATTERN_DEFAULT_WIDTH)
    grid = _blank(columns)
    mid = (columns + 1) // 2
    for row in range(DAYS_PER_WEEK):
        for column in range(mid):
            level = rng.randint(1, TOP_LEVEL) if rng.random() < density else 0
            grid[row][column] = level
            grid[row][columns - 1 - column] = level
    return grid


def _wave(*, width: int | None, rng: random.Random, **_extra: object) -> Grid:
    columns = _require_width(width if width is not None else PATTERN_DEFAULT_WIDTH)
    grid = _blank(columns)
    phase = rng.random() * 2 * math.pi
    period = max(4, min(PATTERN_WAVE_PERIOD, columns))
    for column in range(columns):
        centre = (DAYS_PER_WEEK - 1) / 2 + 2 * math.sin(phase + 2 * math.pi * column / period)
        for row in range(DAYS_PER_WEEK):
            distance = abs(row - centre)
            if distance < 0.6:
                grid[row][column] = TOP_LEVEL
            elif distance < 1.5:
                grid[row][column] = 3
            elif distance < 2.4:
                grid[row][column] = 2
            elif distance < 3.2:
                grid[row][column] = 1
    return grid


def _tetris(*, width: int | None, rng: random.Random, **_extra: object) -> Grid:
    """Stack tetrominoes into a mid-game board with a ragged skyline.

    Pieces fall toward Saturday (the last row). Each piece is one shade,
    chosen so it differs from any orthogonally adjacent piece. The stack
    stays between ``PATTERN_TETRIS_MIN_HEIGHT`` and
    ``PATTERN_TETRIS_MAX_HEIGHT`` rows so the top is uneven, not a full
    board. A falling piece is added above the stack when there is room.
    """
    columns = _require_width(width if width is not None else PATTERN_DEFAULT_WIDTH)
    grid = _blank(columns)
    targets = _skyline(columns, rng)
    for _ in range(columns * DAYS_PER_WEEK):  # more than enough; we stop when nothing fits
        if not _drop_piece(grid, rng, max_heights=targets):
            break
    _spawn_falling_piece(grid, rng)
    return grid


def _skyline(columns: int, rng: random.Random) -> list[int]:
    """Target stack height for each column, ragged between the allowed bounds."""
    low, high = PATTERN_TETRIS_MIN_HEIGHT, PATTERN_TETRIS_MAX_HEIGHT
    height = rng.randint(low, high)
    targets: list[int] = []
    for _ in range(columns):
        height = max(low, min(high, height + rng.choice((-2, -1, -1, 0, 0, 0, 1, 1, 2))))
        targets.append(height)
    if columns >= 3 and max(targets) - min(targets) < 2:
        index = rng.randrange(columns)
        if targets[index] <= (low + high) // 2:
            targets[index] = min(high, targets[index] + 2)
        else:
            targets[index] = max(low, targets[index] - 2)
    return targets


def _drop_piece(
    grid: Grid,
    rng: random.Random,
    max_heights: list[int] | None = None,
) -> bool:
    """Lock one tetromino, or return False if none can spawn."""
    columns = len(grid[0])
    shapes = [rotation for piece in TETROMINOES for rotation in piece]
    rng.shuffle(shapes)
    for cells in shapes:
        piece_width = max(col for _row, col in cells) + 1
        if piece_width > columns:
            continue
        starts = list(range(columns - piece_width + 1))
        rng.shuffle(starts)
        for start in starts:
            row = _drop_row(grid, cells, start)
            if row is None or not _within_skyline(cells, row, start, max_heights):
                continue
            level = _contrasting_level(grid, cells, row, start, rng)
            if level is None:
                continue
            _stamp_piece(grid, cells, row, start, level)
            return True
    return False


def _spawn_falling_piece(grid: Grid, rng: random.Random) -> bool:
    """Lock one tetromino that still has room to fall, if any such placement exists."""
    columns = len(grid[0])
    shapes = [rotation for piece in TETROMINOES for rotation in piece]
    rng.shuffle(shapes)
    for cells in shapes:
        piece_width = max(col for _row, col in cells) + 1
        if piece_width > columns:
            continue
        starts = list(range(columns - piece_width + 1))
        rng.shuffle(starts)
        max_row = DAYS_PER_WEEK - max(drow for drow, _col in cells) - 1
        for start in starts:
            for row in range(max_row):
                if not _fits(grid, cells, row, start):
                    continue
                if not _fits(grid, cells, row + 1, start):
                    continue  # already landed
                level = _contrasting_level(grid, cells, row, start, rng)
                if level is None:
                    continue
                _stamp_piece(grid, cells, row, start, level)
                return True
    return False


def _stamp_piece(
    grid: Grid, cells: tuple[tuple[int, int], ...], row: int, column: int, level: int
) -> None:
    for drow, dcol in cells:
        grid[row + drow][column + dcol] = level


def _within_skyline(
    cells: tuple[tuple[int, int], ...],
    row: int,
    column: int,
    max_heights: list[int] | None,
) -> bool:
    if max_heights is None:
        return True
    for drow, dcol in cells:
        if row + drow < DAYS_PER_WEEK - max_heights[column + dcol]:
            return False
    return True


def _contrasting_level(
    grid: Grid,
    cells: tuple[tuple[int, int], ...],
    row: int,
    column: int,
    rng: random.Random,
) -> int | None:
    """Return a shade that stands out from neighbouring pieces, if any exist.

    Orthogonal neighbours must differ (otherwise the piece would merge with
    them). Diagonal neighbours are avoided when a free shade remains, and
    among the leftover shades the one farthest from its neighbours is
    preferred so pieces stay easy to tell apart.
    """
    orthogonal = _neighbour_levels(grid, cells, row, column, diagonal=False)
    diagonal = _neighbour_levels(grid, cells, row, column, diagonal=True)
    choices = [level for level in range(1, TOP_LEVEL + 1) if level not in diagonal]
    if not choices:
        choices = [level for level in range(1, TOP_LEVEL + 1) if level not in orthogonal]
    if not choices:
        return None
    used = diagonal or orthogonal
    if not used:
        return rng.choice(choices)
    best = max(min(abs(level - other) for other in used) for level in choices)
    return rng.choice(
        [level for level in choices if min(abs(level - other) for other in used) == best]
    )


def _neighbour_levels(
    grid: Grid,
    cells: tuple[tuple[int, int], ...],
    row: int,
    column: int,
    *,
    diagonal: bool,
) -> set[int]:
    height, width = len(grid), len(grid[0])
    body = {(row + drow, column + dcol) for drow, dcol in cells}
    deltas = (
        ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))
        if diagonal
        else ((-1, 0), (1, 0), (0, -1), (0, 1))
    )
    levels: set[int] = set()
    for r, c in body:
        for drow, dcol in deltas:
            nr, nc = r + drow, c + dcol
            if 0 <= nr < height and 0 <= nc < width and (nr, nc) not in body:
                level = grid[nr][nc]
                if level:
                    levels.add(level)
    return levels


def _fits(grid: Grid, cells: tuple[tuple[int, int], ...], row: int, column: int) -> bool:
    height, width = len(grid), len(grid[0])
    for drow, dcol in cells:
        r, c = row + drow, column + dcol
        if c < 0 or c >= width or r >= height or r < 0:
            return False
        if grid[r][c]:
            return False
    return True


def _drop_row(grid: Grid, cells: tuple[tuple[int, int], ...], column: int) -> int | None:
    """Return the landing row for ``cells``, or None if they cannot spawn."""
    if not _fits(grid, cells, 0, column):
        return None
    row = 0
    while _fits(grid, cells, row + 1, column):
        row += 1
    return row


def _text(
    *,
    width: int | None,
    text: str,
    align: str,
    overflow: str,
    **_extra: object,
) -> Grid:
    characters = _normalise_text(text)
    if not characters:
        raise ValueError(
            "The text pattern needs some text: letters A-Z, digits 0-9, spaces, or . , ! ? - ' : /"
        )
    needed = text_width("".join(characters))
    columns = width
    if columns is None:
        columns = min(needed, MAX_WEEKS)
    else:
        columns = _require_width(columns)
    if needed > columns:
        if overflow == PATTERN_OVERFLOW_ERROR:
            raise ValueError(
                f"{text!r} needs {needed} weeks, but the grid is only {columns} "
                f"wide (at most {MAX_WEEKS}). Shorten the text, widen the grid, "
                "or pass overflow='truncate'."
            )
        characters = _truncate(characters, columns)
        needed = text_width("".join(characters))
    grid = _blank(columns)
    if not characters:
        return grid
    origin = 0
    if align == PATTERN_TEXT_ALIGN_CENTER:
        origin = max(0, (columns - needed) // 2)
    elif align != PATTERN_TEXT_ALIGN_LEFT:
        raise ValueError(f"align must be one of: {', '.join(PATTERN_TEXT_ALIGNS)} (got {align!r}).")
    cursor = origin
    for index, char in enumerate(characters):
        _stamp(grid, char, cursor)
        cursor += PATTERN_FONT_WIDTH
        if index != len(characters) - 1:
            cursor += PATTERN_FONT_GAP
    return grid


def _normalise_text(text: str) -> str:
    characters: list[str] = []
    for char in text.strip().upper():
        if char not in PATTERN_FONT:
            raise ValueError(
                f"Unsupported character {char!r} in pattern text. "
                "Use A-Z, 0-9, spaces, or . , ! ? - ' : /"
            )
        characters.append(char)
    return "".join(characters)


def _truncate(characters: str, width: int) -> str:
    """Keep whole glyphs, from the left, that fit in ``width``."""
    kept: list[str] = []
    for char in characters:
        candidate = "".join(kept) + char
        if text_width(candidate) > width:
            break
        kept.append(char)
    return "".join(kept)


def _stamp(grid: Grid, char: str, origin: int) -> None:
    glyph = PATTERN_FONT[char]
    for row, bits in enumerate(glyph):
        if row >= PATTERN_FONT_HEIGHT or row >= len(grid):
            break
        for column in range(PATTERN_FONT_WIDTH):
            if origin + column >= len(grid[0]):
                break
            if bits & (1 << (PATTERN_FONT_WIDTH - 1 - column)):
                grid[row][origin + column] = TOP_LEVEL


GENERATORS: dict[str, PatternGenerator] = {
    PATTERN_RANDOM: _random_noise,
    PATTERN_MIRROR: _mirror,
    PATTERN_WAVE: _wave,
    PATTERN_TETRIS: _tetris,
    PATTERN_TEXT: _text,
}
"""Name to generator; add a theme by putting a function here and a name in PATTERN_NAMES."""


__all__ = ["GENERATORS", "generate", "text_width"]
