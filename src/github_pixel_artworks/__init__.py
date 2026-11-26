"""
github-pixel-artworks

Create pixel artworks in your GitHub contributions chart by generating backdated commits.
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version

try:
    __version__ = pkg_version("github-pixel-artworks")
except PackageNotFoundError:  # running from a source tree without installing
    __version__ = "0.1.0"

# Re-export the main public API from core
from .core import (
    MAX_WEEKS,
    apply_drawing,
    calculate_multiplier,
    fetch_max_daily_commits,
    get_auto_start_date,
    get_first_sunday_of_year,
    grid_to_text,
    load_grid,
    preview,
    save_grid,
)

__all__ = [
    "__version__",
    "MAX_WEEKS",
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
