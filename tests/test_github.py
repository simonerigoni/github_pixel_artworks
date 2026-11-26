"""GitHub username checks, contribution scraping and remote URLs."""

import urllib.error
from pathlib import Path

import git
import pytest

from github_pixel_artworks.github import (
    calculate_multiplier,
    fetch_max_daily_commits,
    normalize_github_https_url,
    resolve_github_repo_url,
)

FIXTURES = Path(__file__).parent / "fixtures"


class FakeResponse:
    def __init__(self, body: str) -> None:
        self._body = body.encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


@pytest.fixture
def serve(monkeypatch: pytest.MonkeyPatch):
    """Replace urlopen with one that returns ``body``; returns the list of requested URLs."""
    requested: list[str] = []

    def install(body: str) -> list[str]:
        def fake_urlopen(url: str, timeout: float) -> FakeResponse:
            requested.append(url)
            return FakeResponse(body)

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        return requested

    return install


def ignore(_message: str) -> None:
    pass


class TestFetchMaxDailyCommits:
    def test_parses_the_real_contribution_calendar_markup(self, serve) -> None:
        # Captured from github.com: the count is in a <tool-tip> beside each <td data-date>.
        serve((FIXTURES / "contributions_snippet.html").read_text(encoding="utf-8"))

        assert fetch_max_daily_commits("simonerigoni", log=ignore) == 12

    def test_handles_singular_and_thousands_separators(self, serve) -> None:
        serve(
            '<tool-tip for="a">1 contribution on May 1st.</tool-tip>\n'
            '<tool-tip for="b">1,234 contributions on May 2nd.</tool-tip>\n'
            '<tool-tip for="c">No contributions on May 3rd.</tool-tip>\n'
        )

        assert fetch_max_daily_commits("someone", log=ignore) == 1234

    def test_returns_none_for_an_empty_calendar(self, serve) -> None:
        serve('<tool-tip for="a">No contributions on May 1st.</tool-tip>')

        assert fetch_max_daily_commits("someone", log=ignore) is None

    @pytest.mark.parametrize("username", ["", "../orgs/x", "a/b", "-dash", "a" * 40, "x?y=1"])
    def test_rejects_invalid_usernames_without_a_request(self, serve, username: str) -> None:
        requested = serve("")
        messages: list[str] = []

        result = fetch_max_daily_commits(username, log=messages.append)

        assert result is None
        assert requested == []
        assert messages[0].startswith("Warning:")

    def test_returns_none_and_warns_when_offline(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def offline(*_args: object, **_kwargs: object) -> None:
            raise urllib.error.URLError("offline")

        monkeypatch.setattr("urllib.request.urlopen", offline)
        messages: list[str] = []

        assert fetch_max_daily_commits("someone", log=messages.append) is None
        assert "offline" in messages[0]


@pytest.mark.parametrize(
    ("max_commits", "multiplier"), [(-3, 1), (0, 1), (4, 1), (5, 2), (8, 2), (9, 3)]
)
def test_calculate_multiplier_rounds_up_to_reach_the_darkest_day(
    max_commits: int, multiplier: int
) -> None:
    assert calculate_multiplier(max_commits) == multiplier


@pytest.mark.parametrize(
    ("remote", "expected"),
    [
        ("git@github.com:owner/repo.git", "https://github.com/owner/repo"),
        ("ssh://git@github.com/owner/repo.git", "https://github.com/owner/repo"),
        ("https://github.com/owner/repo/", "https://github.com/owner/repo"),
        ("http://github.com/owner/repo.git", "https://github.com/owner/repo"),
        ("https://x-access-token:secret@github.com/owner/repo.git", None),
        ("https://gitlab.com/owner/repo.git", None),
    ],
)
def test_normalize_github_https_url(remote: str, expected: str | None) -> None:
    assert normalize_github_https_url(remote) == expected


def test_resolve_github_repo_url_prefers_origin(git_repo: git.Repo) -> None:
    git_repo.create_remote("backup", "git@github.com:someone/backup.git")

    assert resolve_github_repo_url(git_repo) == "https://github.com/someone/canvas"


def test_resolve_github_repo_url_falls_back_to_username(tmp_path: Path) -> None:
    repo = git.Repo.init(tmp_path / "no-remote")

    assert resolve_github_repo_url(repo) is None
    assert (
        resolve_github_repo_url(repo, username="someone")
        == "https://github.com/someone/github_pixel_artworks"
    )
