"""GitHub specifics: usernames, the public contribution calendar, remote URLs and repo checks."""

import json
import math
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

from .config import (
    CONTRIBUTIONS_URL,
    DAY_COUNT_RE,
    FETCH_TIMEOUT_SECONDS,
    GITHUB_REMOTE_PREFIXES,
    GITHUB_URL,
    NOREPLY_RE,
    REPO_API_URL,
    TOP_LEVEL,
    USERNAME_RE,
)


def is_valid_github_username(username: str) -> bool:
    """Return True if ``username`` is a syntactically valid GitHub login."""
    return USERNAME_RE.fullmatch(username) is not None


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

    url = CONTRIBUTIONS_URL.format(username=urllib.parse.quote(username))
    try:
        with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT_SECONDS) as response:
            html = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError) as error:
        log(f"Warning: could not fetch GitHub contributions for '{username}': {error}")
        return None

    counts = [int(count.replace(",", "")) for count in DAY_COUNT_RE.findall(html)]
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
    for prefix in GITHUB_REMOTE_PREFIXES:
        if url.startswith(prefix):
            return GITHUB_URL + url.removeprefix(prefix).strip("/")
    return None


def github_slug(remote_url: str) -> tuple[str, str] | None:
    """Return ``(owner, repo)`` for a GitHub repository URL, else None."""
    url = normalize_github_https_url(remote_url)
    if url is None:
        return None
    parts = url.removeprefix(GITHUB_URL).split("/")
    return (parts[0], parts[1]) if len(parts) == 2 and all(parts) else None


def commit_email_warning(email: str | None, login: str | None) -> str | None:
    """Return a warning if commits made with ``email`` would not count for ``login``.

    GitHub credits a commit to the account its email is linked to. An unset email
    never counts, and a no-reply address names its account, so a different login
    there is a mismatch. Other addresses cannot be checked without signing in.
    """
    if not email:
        return (
            "git user.email is not set, so GitHub cannot link the commits to you. "
            "Set it with: git config user.email <an email on your GitHub account>"
        )
    match = NOREPLY_RE.fullmatch(email.strip())
    if match and login and match["login"].lower() != login.lower():
        return (
            f"git user.email {email} is the no-reply address of '{match['login']}', "
            f"not '{login}', so the art would show on that profile instead."
        )
    return None


def fetch_is_fork(owner: str, repo: str) -> bool | None:
    """Return whether ``owner/repo`` is a fork, using the public GitHub API.

    Returns None when that is unknown: offline, rate limited, or a private repo.
    """
    url = REPO_API_URL.format(owner=urllib.parse.quote(owner), repo=urllib.parse.quote(repo))
    try:
        with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
    except urllib.error.URLError, TimeoutError, ValueError:
        return None
    return bool(data.get("fork")) if isinstance(data, dict) else None
