"""Every named constant of github-pixel-artworks, grouped by what it is about.

The modules that use a constant import it from here; the public ones are still
importable from their original modules too.
"""

import re
from pathlib import Path

# Artwork grid and intensity levels ------------------------------------------

DAYS_PER_WEEK = 7
MAX_WEEKS = 52
"""Widest artwork: one year of the contribution graph."""

TOP_LEVEL = 4
"""Darkest of GitHub's four contribution shades; the GUI paints levels 1 to TOP_LEVEL."""

MAX_FILE_LEVEL = 9
"""Highest level a single character can encode (the digit 9)."""

EMPTY_COLOR = "#ebedf0"
LEVEL_COLORS = {1: "#9be9a8", 2: "#40c463", 3: "#30a14e", TOP_LEVEL: "#216e39"}
"""GitHub's contribution greens. Levels above TOP_LEVEL use the darkest one."""

# Artwork file characters ----------------------------------------------------

EMPTY_CHARS = frozenset(" .xX0")
LEVEL_ONE_CHARS = frozenset("*1")
LEVEL_FOUR_CHARS = frozenset("#hH")
DIGITS = "0123456789"
"""Any digit is its own level; 0 is empty."""

FILLED_PIXEL = "#"
EMPTY_PIXEL = "."
"""Characters of the text preview."""

DATA_DIR = Path("data")
"""Where example artworks live and where the GUI saves drawings."""

# Calendar --------------------------------------------------------------------

SUNDAY = 6
"""``date.weekday()`` value for Sunday; GitHub's weeks start on Sunday."""

DAYS_PER_YEAR = 365

MIN_YEAR = 2000
MAX_YEAR = 2100
"""Range of target years accepted by the CLI and the GUI."""

COMMIT_HOUR_UTC = 12
"""Hour of day (UTC) every pixel commit is dated at.

GitHub groups contributions by UTC day, so noon keeps each pixel on its
intended square whatever the committer's local timezone.
"""

# GitHub ----------------------------------------------------------------------

GITHUB_URL = "https://github.com/"
CONTRIBUTIONS_URL = GITHUB_URL + "users/{username}/contributions"
"""The public contribution calendar of ``username``."""
REPO_API_URL = "https://api.github.com/repos/{owner}/{repo}"
FETCH_TIMEOUT_SECONDS = 15

PROFILE_REPO_URL = GITHUB_URL + "{username}/{username}"
"""The profile README repository of ``username``, the recommended target."""

GITHUB_USER_CONFIG_KEY = "github.user"
"""Git setting checked first when detecting the user's GitHub username."""
GH_COMMAND = "gh"
"""GitHub CLI, asked for the signed-in login when installed (``gh api user``)."""
GH_TIMEOUT_SECONDS = 5
GIT_CONFIG_TIMEOUT_SECONDS = 5
IDENTITY_FIX_HINT = (
    'Set it once with: git config --global user.name "Your Name" and '
    "git config --global user.email <an email on your GitHub account>"
)
"""How to fix a missing git identity, shown before anything is cloned or committed."""
COMMIT_SEARCH_URL = "https://api.github.com/search/commits?q={query}"
"""GitHub's public commit search, asked unauthenticated for the login behind ``user.email``."""
COMMIT_SEARCH_QUERY = "author-email:{email}"
COMMIT_SEARCH_TIMEOUT_SECONDS = 5
API_HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "github_pixel_artworks"}
"""Sent with GitHub API requests; the API rejects requests without a User-Agent."""

GITHUB_REMOTE_PREFIXES = (
    "git@github.com:",
    "ssh://git@github.com/",
    GITHUB_URL,
    "http://github.com/",
)

USERNAME_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}")
"""1 to 39 letters, digits or single inner hyphens.

Also decides whether ``git config user.name`` can be taken as a guess of the
login: it must match in full, so names with spaces never do.
"""

DAY_COUNT_RE = re.compile(r">\s*([\d,]+) contributions? on ")
"""Day tooltip text, e.g. ``12 contributions on May 2nd.`` (``No contributions`` is skipped)."""

NOREPLY_RE = re.compile(r"(?:\d+\+)?(?P<login>[^@+]+)@users\.noreply\.github\.com", re.IGNORECASE)
"""GitHub's no-reply commit address, ``ID+login@users.noreply.github.com`` or ``login@...``."""

# Target repository and art commits ------------------------------------------

CLONE_TEMP_PREFIX = "gh-pixel-art-"
"""Prefix of the temporary folder a URL target is cloned into (``tempfile.mkdtemp``)."""

URL_SCHEMES = ("https://", "http://", "ssh://", "git://", "file://")
"""Targets starting with one of these are cloned rather than opened."""

TOOL_MARKER = Path("src") / "github_pixel_artworks" / "__init__.py"
"""A file only a checkout of this project has."""

ART_MESSAGE_PREFIX = "pixel art "
"""Start of every art commit message, which is also how earlier art is recognised."""

REF_UPDATE_MESSAGE = "github-pixel-artworks"
"""Reflog message when the branch moves to the new art commits."""

PROGRESS_EVERY = 10
"""Log a progress line every this many commits."""

ART_BRANCH_PREFIX = "artworks"
"""Year branches are named ``artworks-<year>``."""

YEAR_BRANCH_PLACEHOLDERS = (ART_BRANCH_PREFIX, "art", "dedicated-art")
"""``--art-branch`` values expanded to ``artworks-<year>`` when ``--year`` is given."""

# CLI exit codes --------------------------------------------------------------

EXIT_DRAWING_FAILED = 2
EXIT_BAD_ARTWORK = 4
EXIT_BAD_ARGUMENT = 5

# GUI -------------------------------------------------------------------------

CELL_SIZE = 18
GRID_BACKGROUND = "#f0f0f0"
CELL_OUTLINE = "#999"
CANVAS_BORDER = "#888"
DARK_LEVEL_TEXT_FROM = 3
"""Level from which the picker button label is white instead of black."""

DEFAULT_COLUMNS = 10
MIN_COLUMNS = 3

WINDOW_SIZE = (1540, 600)
"""Preferred first size: wide enough for a full year of weeks next to both side panes."""
WINDOW_SCREEN_MARGIN = 80
"""Pixels left free on each axis when the screen is smaller than WINDOW_SIZE."""
WINDOW_MIN_SIZE = (720, 400)

DRAWINGS_PANE_WIDTH = 210
DRAWINGS_PANE_MIN_WIDTH = 150
EDITOR_PANE_MIN_WIDTH = 200
"""The grid scrolls horizontally when it is wider than its pane."""
ACTIONS_PANE_WIDTH = 280
ACTIONS_PANE_MIN_WIDTH = 240
"""Side panes keep their width when the window is resized; the grid pane absorbs the change."""
DRAWING_BUTTON_WIDTH = 7
"""Characters; keeps Load, Delete and Refresh on one row of the drawings pane."""
HINT_PADDING = 24
LOG_LINES = 4  # requested Log height; it grows with the window
"""Pixels; hints wrap at the actions pane width minus this."""
HINT_COLOR = "#555"
QUEUE_POLL_MS = 80
STATUS_READY = "Ready"
STATUS_HINT = "Ready - draw on the grid, pick a year and the target repository, then Generate."

# Grid diagram (scripts/render_grid_diagram.py) -------------------------------

DIAGRAM_ARTWORK = DATA_DIR / "heart.txt"
DIAGRAM_OUTPUT = Path("images") / "grid_diagram.svg"
"""Relative to the project root."""
DIAGRAM_YEAR = 2026

DIAGRAM_CELL = 26
DIAGRAM_PITCH = DIAGRAM_CELL + 4
DIAGRAM_GRID_LEFT = 96
DIAGRAM_GRID_TOP = 104
DIAGRAM_LEGEND_GAP = 36
DIAGRAM_RIGHT_MARGIN = 300
DIAGRAM_BOTTOM_MARGIN = 60
DIAGRAM_MUTED = "#57606a"
DIAGRAM_DAY_NAMES = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")
DIAGRAM_LEGEND = (
    ("space . x 0", "no commits"),
    ("* 1", "1 x multiplier"),
    ("2", "2 x multiplier"),
    ("3", "3 x multiplier"),
    ("4 # H", "4 x multiplier"),
)
"""File characters and what they become."""
