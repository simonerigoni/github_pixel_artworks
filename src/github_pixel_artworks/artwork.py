"""Artwork grids: the 7-row text format, intensity levels and drawing files."""

from pathlib import Path

from .config import (
    DAYS_PER_WEEK,
    DIGITS,
    EMPTY_CHARS,
    EMPTY_COLOR,
    LEVEL_COLORS,
    LEVEL_FOUR_CHARS,
    LEVEL_ONE_CHARS,
    MAX_FILE_LEVEL,
    MAX_WEEKS,
    TOP_LEVEL,
)

type Grid = list[list[int]]
"""Seven rows (Sunday first) of intensity levels, one column per week. 0 means empty."""


def load_grid(path: Path | str) -> Grid:
    """Load an artwork file.

    The file has exactly 7 lines (Sunday to Saturday); each character is one
    week. Trailing blank lines are ignored and short lines are padded with
    empty cells. Characters map to levels as follows:

    - empty: space, ``.``, ``x``, ``X``, ``0``
    - level 1: ``*``, ``1``
    - levels 2 to 9: the digit itself
    - level 4: ``#``, ``h``, ``H``

    Any other character is empty.

    Raises:
        FileNotFoundError: if ``path`` does not exist.
        ValueError: if the file does not have 7 rows or is 0 or more than
            ``MAX_WEEKS`` columns wide.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Artwork file not found: {path}")

    rows = path.read_text(encoding="utf-8", errors="replace").splitlines()
    while len(rows) > DAYS_PER_WEEK and not rows[-1].strip():
        rows.pop()
    if len(rows) != DAYS_PER_WEEK:
        raise ValueError(
            f"Artwork must have exactly {DAYS_PER_WEEK} rows (days of week). "
            f"Got {len(rows)} in {path}"
        )

    width = max(len(row) for row in rows)
    if width == 0:
        raise ValueError(f"Artwork has zero width: {path}")
    if width > MAX_WEEKS:
        raise ValueError(
            f"Artwork must have at most {MAX_WEEKS} weeks (columns). Got {width} in {path}"
        )
    return [[char_to_level(char) for char in row.ljust(width)] for row in rows]


def char_to_level(char: str) -> int:
    """Return the intensity level encoded by one artwork character."""
    if char in EMPTY_CHARS:
        return 0
    if char in LEVEL_ONE_CHARS:
        return 1
    if char in LEVEL_FOUR_CHARS:
        return TOP_LEVEL
    if char in DIGITS:
        return int(char)
    return 0


def level_to_char(level: int) -> str:
    """Return the canonical character for ``level`` (clamped to ``MAX_FILE_LEVEL``)."""
    if level <= 0:
        return " "
    if level == 1:
        return "*"
    return str(min(level, MAX_FILE_LEVEL))


def grid_to_text(grid: Grid) -> str:
    """Serialise ``grid`` in the format read by :func:`load_grid`.

    Lossless for levels 0 to 9. Level 1 is written as ``*`` so level-1 art
    matches the shipped examples.
    """
    return "".join("".join(level_to_char(level) for level in row) + "\n" for row in grid)


def save_grid(path: Path | str, grid: Grid) -> None:
    """Write ``grid`` to ``path``, creating parent directories as needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(grid_to_text(grid), encoding="utf-8")


def drawing_path(data_dir: Path | str, name: str) -> Path:
    """Return ``data_dir/<name>.txt`` for a drawing name typed by the user.

    An empty name becomes ``untitled`` and a trailing ``.txt`` is optional.

    Raises:
        ValueError: if the name contains a path separator, a drive colon or is
            ``.``/``..``, so a drawing can never be written outside ``data_dir``.
    """
    stem = name.strip() or "untitled"
    stem = stem.removesuffix(".txt")
    if stem in ("", ".", "..") or any(sep in stem for sep in ("/", "\\", ":")):
        raise ValueError(f"Invalid drawing name: {name!r} (use a plain file name)")
    return Path(data_dir) / f"{stem}.txt"


def validate_grid(grid: Grid) -> None:
    """Raise ValueError unless ``grid`` has 7 rows of the same, non-zero width."""
    if len(grid) != DAYS_PER_WEEK or not grid[0]:
        raise ValueError(f"grid must have exactly {DAYS_PER_WEEK} non-empty rows")
    if any(len(row) != len(grid[0]) for row in grid):
        raise ValueError("grid rows must all have the same width")


def level_color(level: int) -> str:
    """Return the display colour for ``level`` (empty for 0, darkest above TOP_LEVEL)."""
    if level <= 0:
        return EMPTY_COLOR
    return LEVEL_COLORS[min(level, TOP_LEVEL)]


def count_commits(grid: Grid, multiplier: int = 1) -> int:
    """Return how many commits drawing ``grid`` creates."""
    return sum(sum(row) for row in grid) * multiplier
