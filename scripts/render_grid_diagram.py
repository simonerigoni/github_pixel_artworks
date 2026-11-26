"""Render images/grid_diagram.svg: how an artwork file maps onto contribution days.

The figure uses the package's own loader and date logic, so it always matches
what the tool does. Run with ``uv run python scripts/render_grid_diagram.py``.
"""

from datetime import timedelta
from html import escape
from pathlib import Path

from github_pixel_artworks.artwork import DAYS_PER_WEEK, level_color, load_grid
from github_pixel_artworks.dates import COMMIT_HOUR_UTC, get_first_sunday_of_year

ROOT = Path(__file__).resolve().parents[1]
ARTWORK = ROOT / "data" / "heart.txt"
OUTPUT = ROOT / "images" / "grid_diagram.svg"
YEAR = 2026

CELL = 26
PITCH = CELL + 4
GRID_LEFT = 96
GRID_TOP = 104
LEGEND_GAP = 36
RIGHT_MARGIN = 300
BOTTOM_MARGIN = 60
MUTED = "#57606a"
DAY_NAMES = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")
LEGEND = (
    ("space . x 0", "no commits"),
    ("* 1", "1 x multiplier"),
    ("2", "2 x multiplier"),
    ("3", "3 x multiplier"),
    ("4 # H", "4 x multiplier"),
)


def text(x: float, y: float, content: str, **attrs: str) -> str:
    """Return an SVG ``<text>``; underscores in attribute names become hyphens."""
    rendered = "".join(f' {key.replace("_", "-")}="{value}"' for key, value in attrs.items())
    return f'<text x="{x}" y="{y}"{rendered}>{escape(content)}</text>'


def square(x: float, y: float, color: str) -> str:
    return f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="4" fill="{color}"/>'


def render() -> str:
    """Return the SVG markup for the diagram."""
    grid = load_grid(ARTWORK)
    weeks = len(grid[0])
    start = get_first_sunday_of_year(YEAR)
    end = start + timedelta(weeks=weeks - 1, days=DAYS_PER_WEEK - 1)
    width = GRID_LEFT + weeks * PITCH + RIGHT_MARGIN
    height = GRID_TOP + DAYS_PER_WEEK * PITCH + BOTTOM_MARGIN

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="Helvetica, Arial, sans-serif" '
        'font-size="13" fill="#24292f">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        text(16, 28, f"data/{ARTWORK.name} with --year {YEAR}", font_weight="bold"),
        text(
            16, 50, "Each column is a week starting on Sunday; each row is a weekday.", fill=MUTED
        ),
    ]
    for day, name in enumerate(DAY_NAMES):
        parts.append(
            text(GRID_LEFT - 12, GRID_TOP + day * PITCH + CELL * 0.68, name, text_anchor="end")
        )

    previous_month = None
    for week in range(weeks):
        sunday = start + timedelta(weeks=week)
        x = GRID_LEFT + week * PITCH
        if sunday.month != previous_month:
            parts.append(text(x, GRID_TOP - 28, sunday.strftime("%b"), fill=MUTED))
            previous_month = sunday.month
        parts.append(
            text(x + CELL / 2, GRID_TOP - 8, str(sunday.day), text_anchor="middle", fill=MUTED)
        )
        for day in range(DAYS_PER_WEEK):
            parts.append(square(x, GRID_TOP + day * PITCH, level_color(grid[day][week])))

    legend_x = GRID_LEFT + weeks * PITCH + LEGEND_GAP
    parts.append(text(legend_x, GRID_TOP - 8, "Character: commits per day", font_weight="bold"))
    for level, (chars, meaning) in enumerate(LEGEND):
        y = GRID_TOP + level * PITCH
        parts.append(square(legend_x, y, level_color(level)))
        parts.append(text(legend_x + CELL + 10, y + CELL * 0.68, f"{chars}: {meaning}"))

    parts.append(
        text(
            16,
            height - 20,
            f"Span: {start.date()} (Sun) to {end.date()} (Sat). "
            f"Each commit is dated {COMMIT_HOUR_UTC}:00 UTC on its day.",
            fill=MUTED,
        )
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main() -> None:
    """Write the diagram to images/grid_diagram.svg."""
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(render(), encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
