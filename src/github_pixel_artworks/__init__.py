"""
github-pixel-artworks

Create pixel artworks in your GitHub contributions chart by generating backdated commits.
"""

try:
    from importlib.metadata import version as pkg_version

    __version__ = pkg_version("github-pixel-artworks")
except Exception:
    __version__ = "0.1.0"

# Re-export the main public API from core
from .core import (
    load_grid,
    save_grid,
    grid_to_text,
    preview,
    get_first_sunday_of_year,
    get_auto_start_date,
    apply_drawing,
    fetch_max_daily_commits,
    calculate_multiplier,
)

__all__ = [
    "__version__",
    "load_grid",
    "save_grid",
    "grid_to_text",
    "preview",
    "get_first_sunday_of_year",
    "get_auto_start_date",
    "apply_drawing",
    "fetch_max_daily_commits",
    "calculate_multiplier",
]
