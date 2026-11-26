"""Render images/grid_diagram.svg: how an artwork file maps onto contribution days.

The figure uses the package's own loader and date logic, so it always matches
what the tool does. Run with ``uv run python scripts/render_grid_diagram.py``.
"""

from datetime import timedelta
from html import escape
from pathlib import Path

from github_pixel_artworks.artwork import level_color, load_grid
from github_pixel_artworks.config import (
    COMMIT_HOUR_UTC,
    DAYS_PER_WEEK,
    DIAGRAM_ARTWORK,
    DIAGRAM_BOTTOM_MARGIN,
    DIAGRAM_CELL,
    DIAGRAM_DAY_NAMES,
    DIAGRAM_GRID_LEFT,
    DIAGRAM_GRID_TOP,
    DIAGRAM_LEGEND,
    DIAGRAM_LEGEND_GAP,
    DIAGRAM_MUTED,
    DIAGRAM_OUTPUT,
    DIAGRAM_PITCH,
    DIAGRAM_RIGHT_MARGIN,
    DIAGRAM_YEAR,
)
from github_pixel_artworks.dates import get_first_sunday_of_year

ROOT = Path(__file__).resolve().parents[1]


def text(x: float, y: float, content: str, **attrs: str) -> str:
    """Return an SVG ``<text>``; underscores in attribute names become hyphens."""
    rendered = "".join(f' {key.replace("_", "-")}="{value}"' for key, value in attrs.items())
    return f'<text x="{x}" y="{y}"{rendered}>{escape(content)}</text>'


def square(x: float, y: float, color: str) -> str:
    return f'<rect x="{x}" y="{y}" width="{DIAGRAM_CELL}" height="{DIAGRAM_CELL}" rx="4" fill="{color}"/>'


def render() -> str:
    """Return the SVG markup for the diagram."""
    grid = load_grid(ROOT / DIAGRAM_ARTWORK)
    weeks = len(grid[0])
    start = get_first_sunday_of_year(DIAGRAM_YEAR)
    end = start + timedelta(weeks=weeks - 1, days=DAYS_PER_WEEK - 1)
    width = DIAGRAM_GRID_LEFT + weeks * DIAGRAM_PITCH + DIAGRAM_RIGHT_MARGIN
    height = DIAGRAM_GRID_TOP + DAYS_PER_WEEK * DIAGRAM_PITCH + DIAGRAM_BOTTOM_MARGIN

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="Helvetica, Arial, sans-serif" '
        'font-size="13" fill="#24292f">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        text(
            16, 28, f"{DIAGRAM_ARTWORK.as_posix()} with --year {DIAGRAM_YEAR}", font_weight="bold"
        ),
        text(
            16,
            50,
            "Each column is a week starting on Sunday; each row is a weekday.",
            fill=DIAGRAM_MUTED,
        ),
    ]
    for day, name in enumerate(DIAGRAM_DAY_NAMES):
        parts.append(
            text(
                DIAGRAM_GRID_LEFT - 12,
                DIAGRAM_GRID_TOP + day * DIAGRAM_PITCH + DIAGRAM_CELL * 0.68,
                name,
                text_anchor="end",
            )
        )

    previous_month = None
    for week in range(weeks):
        sunday = start + timedelta(weeks=week)
        x = DIAGRAM_GRID_LEFT + week * DIAGRAM_PITCH
        if sunday.month != previous_month:
            parts.append(text(x, DIAGRAM_GRID_TOP - 28, sunday.strftime("%b"), fill=DIAGRAM_MUTED))
            previous_month = sunday.month
        parts.append(
            text(
                x + DIAGRAM_CELL / 2,
                DIAGRAM_GRID_TOP - 8,
                str(sunday.day),
                text_anchor="middle",
                fill=DIAGRAM_MUTED,
            )
        )
        for day in range(DAYS_PER_WEEK):
            parts.append(
                square(x, DIAGRAM_GRID_TOP + day * DIAGRAM_PITCH, level_color(grid[day][week]))
            )

    legend_x = DIAGRAM_GRID_LEFT + weeks * DIAGRAM_PITCH + DIAGRAM_LEGEND_GAP
    parts.append(
        text(legend_x, DIAGRAM_GRID_TOP - 8, "Character: commits per day", font_weight="bold")
    )
    for level, (chars, meaning) in enumerate(DIAGRAM_LEGEND):
        y = DIAGRAM_GRID_TOP + level * DIAGRAM_PITCH
        parts.append(square(legend_x, y, level_color(level)))
        parts.append(
            text(legend_x + DIAGRAM_CELL + 10, y + DIAGRAM_CELL * 0.68, f"{chars}: {meaning}")
        )

    parts.append(
        text(
            16,
            height - 20,
            f"Span: {start.date()} (Sun) to {end.date()} (Sat). "
            f"Each commit is dated {COMMIT_HOUR_UTC}:00 UTC on its day.",
            fill=DIAGRAM_MUTED,
        )
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main() -> None:
    """Write the diagram to images/grid_diagram.svg."""
    output = ROOT / DIAGRAM_OUTPUT
    output.parent.mkdir(exist_ok=True)
    output.write_text(render(), encoding="utf-8")
    print(f"Wrote {DIAGRAM_OUTPUT.as_posix()}")


if __name__ == "__main__":
    main()
