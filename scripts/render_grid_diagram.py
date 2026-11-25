"""Render images/grid_diagram.svg: how an artwork file maps onto contribution days.

The figure is generated from the package itself (load_grid, get_first_sunday_of_year),
so it always matches the real date logic. Run with:

    uv run python scripts/render_grid_diagram.py
"""

from datetime import timedelta
from html import escape
from pathlib import Path

from github_pixel_artworks.core import get_first_sunday_of_year, load_grid

ROOT = Path(__file__).resolve().parents[1]
ARTWORK = ROOT / "data" / "heart.txt"
OUTPUT = ROOT / "images" / "grid_diagram.svg"
YEAR = 2026

CELL = 26
GAP = 4
LEFT = 96
TOP = 104
DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
EMPTY_COLOR = "#ebedf0"
LEVEL_COLORS = {1: "#9be9a8", 2: "#40c463", 3: "#30a14e", 4: "#216e39"}
LEGEND_CHARS = {1: "* 1", 2: "2", 3: "3", 4: "4 # H"}


def _text(x: float, y: float, content: str, **attrs: str) -> str:
    extra = "".join(f' {key.replace("_", "-")}="{value}"' for key, value in attrs.items())
    return f'<text x="{x}" y="{y}"{extra}>{escape(content)}</text>'


def render() -> str:
    """Return the SVG markup for the diagram."""
    grid = load_grid(ARTWORK)
    weeks = len(grid[0])
    start = get_first_sunday_of_year(YEAR)
    pitch = CELL + GAP
    width = LEFT + weeks * pitch + 300
    height = TOP + 7 * pitch + 60

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="Helvetica, Arial, sans-serif" '
        'font-size="13" fill="#24292f">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        _text(16, 28, f"data/{ARTWORK.name} with --year {YEAR}", font_weight="bold"),
        _text(
            16,
            50,
            "Each column is a week (starting on Sunday), each row a weekday.",
            fill="#57606a",
        ),
    ]
    for day, name in enumerate(DAY_NAMES):
        parts.append(_text(LEFT - 12, TOP + day * pitch + CELL * 0.68, name, text_anchor="end"))
    previous_month = None
    for week in range(weeks):
        sunday = start + timedelta(weeks=week)
        x = LEFT + week * pitch
        if sunday.month != previous_month:  # month name where a new month starts, like GitHub
            parts.append(_text(x, TOP - 28, sunday.strftime("%b"), fill="#57606a"))
            previous_month = sunday.month
        parts.append(
            _text(x + CELL / 2, TOP - 8, str(sunday.day), text_anchor="middle", fill="#57606a")
        )
        for day in range(7):
            level = grid[day][week]
            color = LEVEL_COLORS[min(level, 4)] if level else EMPTY_COLOR
            y = TOP + day * pitch
            parts.append(
                f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="4" fill="{color}"/>'
            )

    legend_x = LEFT + weeks * pitch + 36
    parts.append(_text(legend_x, TOP - 8, "Character: commits per day", font_weight="bold"))
    legend = [("space . x 0: no commits", EMPTY_COLOR)] + [
        (f"{LEGEND_CHARS[level]}: {level} x multiplier", color)
        for level, color in LEVEL_COLORS.items()
    ]
    for row, (label, color) in enumerate(legend):
        y = TOP + row * pitch
        parts.append(
            f'<rect x="{legend_x}" y="{y}" width="{CELL}" height="{CELL}" rx="4" fill="{color}"/>'
        )
        parts.append(_text(legend_x + CELL + 10, y + CELL * 0.68, label))

    last = start + timedelta(weeks=weeks - 1, days=6)
    parts.append(
        _text(
            16,
            height - 20,
            f"Span: {start.date()} (Sun) to {last.date()} (Sat). Each commit is dated 12:00 UTC on its day.",
            fill="#57606a",
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
