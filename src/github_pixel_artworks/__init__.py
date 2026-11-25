"""Draw pixel art on your GitHub contribution graph with backdated commits."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _package_version

try:
    __version__ = _package_version("github-pixel-artworks")
except PackageNotFoundError:  # running from a source tree without installing
    __version__ = "0.1.0"

from .artwork import MAX_WEEKS, drawing_path, grid_to_text, load_grid, save_grid
from .dates import get_auto_start_date, get_first_sunday_of_year
from .github import calculate_multiplier, fetch_max_daily_commits
from .painter import apply_drawing, preview

__all__ = [
    "MAX_WEEKS",
    "__version__",
    "apply_drawing",
    "calculate_multiplier",
    "drawing_path",
    "fetch_max_daily_commits",
    "get_auto_start_date",
    "get_first_sunday_of_year",
    "grid_to_text",
    "load_grid",
    "preview",
    "save_grid",
]
