"""GitHub specifics: usernames, the public contribution calendar, remote URLs and repo checks."""

import json
import math
import os
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

from .config import (
    CONTRIBUTIONS_URL,
    DAY_COUNT_RE,
    FETCH_TIMEOUT_SECONDS,
    GH_COMMAND,
    GH_TIMEOUT_SECONDS,
    GIT_CONFIG_TIMEOUT_SECONDS,
    GITHUB_REMOTE_PREFIXES,
    GITHUB_URL,
    GITHUB_USER_CONFIG_KEY,
    NOREPLY_RE,
    PROFILE_REPO_URL,
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


def profile_repo_url(username: str) -> str:
    """Return the URL of the profile README repository of ``username``."""
    return PROFILE_REPO_URL.format(username=username)


def detect_github_username() -> tuple[str, str] | None:
    """Return ``(username, source)`` from the local settings, or None.

    The first valid hit wins: the global ``git config github.user``, the login in
    a no-reply ``user.email``, then ``gh api user`` if the GitHub CLI is
    installed. Only ``gh`` may use the network, and any failure means no hit.
    """
    user = _git_global_config(GITHUB_USER_CONFIG_KEY)
    if user and is_valid_github_username(user):
        return user, f"git config {GITHUB_USER_CONFIG_KEY}"
    email = _git_global_config("user.email")
    match = NOREPLY_RE.fullmatch(email) if email else None
    if match and is_valid_github_username(match["login"]):
        return match["login"], "the no-reply git user.email"
    login = _gh_login()
    if login and is_valid_github_username(login):
        return login, "gh api user"
    return None


def _git_global_config(key: str) -> str | None:
    command = ["git", "config", "--global", "--get", key]
    return _run(command, GIT_CONFIG_TIMEOUT_SECONDS)


def _gh_login() -> str | None:
    """Return the login gh is signed in as, or None if gh is missing or not signed in."""
    gh = shutil.which(GH_COMMAND)
    return _run([gh, "api", "user", "--jq", ".login"], GH_TIMEOUT_SECONDS) if gh else None


def _run(command: list[str], timeout: float) -> str | None:
    """Return the stripped output of ``command``, or None if it fails or times out."""
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env={**os.environ, "GH_PROMPT_DISABLED": "1"},
        )
    except OSError, subprocess.TimeoutExpired:
        return None
    output = result.stdout.strip()
    return output if result.returncode == 0 and output else None
