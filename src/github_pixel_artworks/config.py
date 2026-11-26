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

TARGET_CLONE_DIR_NAME = "target_cloned_repo"
"""Folder at the tool's project root that a URL target is cloned into, as ``<this>/<repo>``.

The project root is found from the package location (see ``art_repo.tool_project_root``),
so the path does not depend on the working directory. The folder is gitignored.
"""

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

# Pattern generators ----------------------------------------------------------

PATTERN_RANDOM = "random"
PATTERN_MIRROR = "mirror"
PATTERN_WAVE = "wave"
PATTERN_TETRIS = "tetris"
PATTERN_TEXT = "text"
PATTERN_NAMES = (PATTERN_RANDOM, PATTERN_MIRROR, PATTERN_WAVE, PATTERN_TETRIS, PATTERN_TEXT)
"""Themes offered by the CLI ``--pattern`` flag and the GUI pattern control."""

PATTERN_DEFAULT_WIDTH = 20
PATTERN_DEFAULT_DENSITY = 0.45
"""Share of cells filled by the random and mirror patterns."""
PATTERN_WAVE_PERIOD = 13
"""Week period of the sine wave pattern."""
PATTERN_TETRIS_MIN_HEIGHT = 1
PATTERN_TETRIS_TYPICAL_HEIGHT = 4
PATTERN_TETRIS_MAX_HEIGHT = 5
"""Grounded stack height, in rows from Saturday: mostly 1-4, occasionally one taller."""
PATTERN_TETRIS_DENSITY = 0.35
"""Default Tetris density: the share of columns that belong to a stack cluster (sparse)."""
PATTERN_TETRIS_CLUSTER_MIN = 3
PATTERN_TETRIS_CLUSTER_MAX = 7
"""Width in columns of one pile of pieces; gaps between piles come from density."""
PATTERN_TEXT_ALIGN_CENTER = "center"
PATTERN_TEXT_ALIGN_LEFT = "left"
PATTERN_TEXT_ALIGNS = (PATTERN_TEXT_ALIGN_CENTER, PATTERN_TEXT_ALIGN_LEFT)
PATTERN_OVERFLOW_ERROR = "error"
PATTERN_OVERFLOW_TRUNCATE = "truncate"
PATTERN_OVERFLOWS = (PATTERN_OVERFLOW_ERROR, PATTERN_OVERFLOW_TRUNCATE)

# 5x7 glyphs, one row per integer; bit 4 is the leftmost pixel.
PATTERN_FONT_WIDTH = 5
PATTERN_FONT_HEIGHT = 7
PATTERN_FONT_GAP = 1
PATTERN_FONT: dict[str, tuple[int, int, int, int, int, int, int]] = {
    "A": (0b01110, 0b10001, 0b10001, 0b11111, 0b10001, 0b10001, 0b10001),
    "B": (0b11110, 0b10001, 0b10001, 0b11110, 0b10001, 0b10001, 0b11110),
    "C": (0b01110, 0b10001, 0b10000, 0b10000, 0b10000, 0b10001, 0b01110),
    "D": (0b11110, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b11110),
    "E": (0b11111, 0b10000, 0b10000, 0b11110, 0b10000, 0b10000, 0b11111),
    "F": (0b11111, 0b10000, 0b10000, 0b11110, 0b10000, 0b10000, 0b10000),
    "G": (0b01110, 0b10001, 0b10000, 0b10111, 0b10001, 0b10001, 0b01110),
    "H": (0b10001, 0b10001, 0b10001, 0b11111, 0b10001, 0b10001, 0b10001),
    "I": (0b01110, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b01110),
    "J": (0b00111, 0b00010, 0b00010, 0b00010, 0b00010, 0b10010, 0b01100),
    "K": (0b10001, 0b10010, 0b10100, 0b11000, 0b10100, 0b10010, 0b10001),
    "L": (0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b11111),
    "M": (0b10001, 0b11011, 0b10101, 0b10101, 0b10001, 0b10001, 0b10001),
    "N": (0b10001, 0b11001, 0b10101, 0b10011, 0b10001, 0b10001, 0b10001),
    "O": (0b01110, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b01110),
    "P": (0b11110, 0b10001, 0b10001, 0b11110, 0b10000, 0b10000, 0b10000),
    "Q": (0b01110, 0b10001, 0b10001, 0b10001, 0b10101, 0b10010, 0b01101),
    "R": (0b11110, 0b10001, 0b10001, 0b11110, 0b10100, 0b10010, 0b10001),
    "S": (0b01110, 0b10001, 0b10000, 0b01110, 0b00001, 0b10001, 0b01110),
    "T": (0b11111, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100),
    "U": (0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b01110),
    "V": (0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b01010, 0b00100),
    "W": (0b10001, 0b10001, 0b10001, 0b10101, 0b10101, 0b10101, 0b01010),
    "X": (0b10001, 0b10001, 0b01010, 0b00100, 0b01010, 0b10001, 0b10001),
    "Y": (0b10001, 0b10001, 0b01010, 0b00100, 0b00100, 0b00100, 0b00100),
    "Z": (0b11111, 0b00001, 0b00010, 0b00100, 0b01000, 0b10000, 0b11111),
    "0": (0b01110, 0b10001, 0b10011, 0b10101, 0b11001, 0b10001, 0b01110),
    "1": (0b00100, 0b01100, 0b00100, 0b00100, 0b00100, 0b00100, 0b01110),
    "2": (0b01110, 0b10001, 0b00001, 0b00010, 0b00100, 0b01000, 0b11111),
    "3": (0b01110, 0b10001, 0b00001, 0b00110, 0b00001, 0b10001, 0b01110),
    "4": (0b00010, 0b00110, 0b01010, 0b10010, 0b11111, 0b00010, 0b00010),
    "5": (0b11111, 0b10000, 0b11110, 0b00001, 0b00001, 0b10001, 0b01110),
    "6": (0b01110, 0b10001, 0b10000, 0b11110, 0b10001, 0b10001, 0b01110),
    "7": (0b11111, 0b00001, 0b00010, 0b00100, 0b01000, 0b01000, 0b01000),
    "8": (0b01110, 0b10001, 0b10001, 0b01110, 0b10001, 0b10001, 0b01110),
    "9": (0b01110, 0b10001, 0b10001, 0b01111, 0b00001, 0b10001, 0b01110),
    " ": (0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000),
    ".": (0b00000, 0b00000, 0b00000, 0b00000, 0b00000, 0b01100, 0b01100),
    ",": (0b00000, 0b00000, 0b00000, 0b00000, 0b01100, 0b01100, 0b01000),
    "!": (0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b00000, 0b00100),
    "?": (0b01110, 0b10001, 0b00001, 0b00010, 0b00100, 0b00000, 0b00100),
    "-": (0b00000, 0b00000, 0b00000, 0b11111, 0b00000, 0b00000, 0b00000),
    "'": (0b00100, 0b00100, 0b00000, 0b00000, 0b00000, 0b00000, 0b00000),
    ":": (0b00000, 0b00100, 0b00000, 0b00000, 0b00000, 0b00100, 0b00000),
    "/": (0b00001, 0b00010, 0b00010, 0b00100, 0b01000, 0b01000, 0b10000),
}
"""Uppercase letters, digits and a few punctuation marks for the text pattern."""

# Each tetromino is the rotations of four (row, column) offsets from a bounding box.
type _Cells = tuple[tuple[int, int], ...]
TETROMINOES: tuple[tuple[_Cells, ...], ...] = (
    (((0, 0), (0, 1), (0, 2), (0, 3)), ((0, 0), (1, 0), (2, 0), (3, 0))),  # I
    (((0, 0), (0, 1), (1, 0), (1, 1)),),  # O
    (  # T
        ((0, 1), (1, 0), (1, 1), (1, 2)),
        ((0, 0), (1, 0), (1, 1), (2, 0)),
        ((0, 0), (0, 1), (0, 2), (1, 1)),
        ((0, 1), (1, 0), (1, 1), (2, 1)),
    ),
    (((0, 1), (0, 2), (1, 0), (1, 1)), ((0, 0), (1, 0), (1, 1), (2, 1))),  # S
    (((0, 0), (0, 1), (1, 1), (1, 2)), ((0, 1), (1, 0), (1, 1), (2, 0))),  # Z
    (  # J
        ((0, 0), (1, 0), (1, 1), (1, 2)),
        ((0, 0), (0, 1), (1, 0), (2, 0)),
        ((0, 0), (0, 1), (0, 2), (1, 2)),
        ((0, 1), (1, 1), (2, 0), (2, 1)),
    ),
    (  # L
        ((0, 2), (1, 0), (1, 1), (1, 2)),
        ((0, 0), (1, 0), (2, 0), (2, 1)),
        ((0, 0), (0, 1), (0, 2), (1, 0)),
        ((0, 0), (0, 1), (1, 1), (2, 1)),
    ),
)
"""The seven tetrominoes, each as the rotations used by the tetris pattern."""

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
STATUS_HINT = (
    "Ready - draw on the grid, pick a year and the target repository, then Generate Commits."
)
GENERATE_BUTTON_TEXT = "Generate Commits"
"""Label of the button that adds the art commits, and of its confirmation dialogs."""

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
