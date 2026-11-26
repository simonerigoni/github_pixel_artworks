"""GitHub specifics: usernames, the public contribution calendar and remote URLs."""

import math
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

import git
from git.exc import GitCommandError

from .artwork import TOP_LEVEL

FETCH_TIMEOUT_SECONDS = 15
DEFAULT_FALLBACK_REPO_NAME = "github_pixel_artworks"

_USERNAME_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}")
"""1 to 39 letters, digits or single inner hyphens."""

_DAY_COUNT_RE = re.compile(r">\s*([\d,]+) contributions? on ")
"""Day tooltip text, e.g. ``12 contributions on May 2nd.`` (``No contributions`` is skipped)."""

_GITHUB_REMOTE_PREFIXES = (
    "git@github.com:",
    "ssh://git@github.com/",
    "https://github.com/",
    "http://github.com/",
)


def is_valid_github_username(username: str) -> bool:
    """Return True if ``username`` is a syntactically valid GitHub login."""
    return _USERNAME_RE.fullmatch(username) is not None


def fetch_max_daily_commits(username: str, log: Callable[[str], None] = print) -> int | None:
    """Return the highest number of contributions ``username`` made on one day.

    Reads the public contribution calendar, so private contributions only count
    if the user shows them on their profile. Returns None, after logging a
    warning, when the username is invalid or the page cannot be fetched, and
    None when the calendar has no contributions.
    """
    if not is_valid_github_username(username):
        log(f"Warning: '{username}' is not a valid GitHub username; skipping auto-scaling.")
        return None

    url = f"https://github.com/users/{urllib.parse.quote(username)}/contributions"
    try:
        with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT_SECONDS) as response:
            html = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError) as error:
        log(f"Warning: could not fetch GitHub contributions for '{username}': {error}")
        return None

    counts = [int(count.replace(",", "")) for count in _DAY_COUNT_RE.findall(html)]
    return max(counts, default=0) or None


def calculate_multiplier(max_commits: int) -> int:
    """Return the multiplier that makes the top level match ``max_commits`` commits a day.

    With it, a level-4 pixel is at least as dark as the user's darkest existing square.
    """
    return max(1, math.ceil(max_commits / TOP_LEVEL))


def normalize_github_https_url(remote_url: str) -> str | None:
    """Return ``https://github.com/<owner>/<repo>`` for a GitHub remote URL, else None.

    URLs with embedded credentials are not recognised, so a token can never end up
    in generated text.
    """
    url = remote_url.strip().removesuffix("/").removesuffix(".git")
    for prefix in _GITHUB_REMOTE_PREFIXES:
        if url.startswith(prefix):
            return f"https://github.com/{url.removeprefix(prefix).strip('/')}"
    return None


def resolve_github_repo_url(
    repo: git.Repo,
    username: str | None = None,
    fallback_repo_name: str = DEFAULT_FALLBACK_REPO_NAME,
) -> str | None:
    """Return the GitHub URL of ``repo``, best effort.

    Uses the ``origin`` remote, then any other GitHub remote, then
    ``https://github.com/<username>/<fallback_repo_name>`` when ``username`` is given.
    """
    for remote in sorted(repo.remotes, key=lambda remote: remote.name != "origin"):
        try:
            url = normalize_github_https_url(remote.url)
        except GitCommandError:  # remote without a URL
            continue
        if url:
            return url
    if username:
        return f"https://github.com/{username}/{fallback_repo_name}"
    return None
