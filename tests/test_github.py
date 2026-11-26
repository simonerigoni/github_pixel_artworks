"""GitHub username checks, contribution scraping, remote URLs and repository checks."""

import json
import urllib.error
import urllib.request
from pathlib import Path

import git
import pytest

from github_pixel_artworks.github import (
    calculate_multiplier,
    commit_email_warning,
    detect_github_username,
    fetch_is_fork,
    fetch_max_daily_commits,
    github_slug,
    normalize_github_https_url,
    profile_repo_url,
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

    def test_returns_none_and_warns_when_offline(self) -> None:
        messages: list[str] = []

        assert fetch_max_daily_commits("someone", log=messages.append) is None
        assert "network disabled" in messages[0]


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


@pytest.mark.parametrize(
    ("remote", "expected"),
    [
        ("git@github.com:owner/repo.git", ("owner", "repo")),
        ("https://github.com/owner/repo", ("owner", "repo")),
        ("https://github.com/owner", None),
        ("https://gitlab.com/owner/repo.git", None),
    ],
)
def test_github_slug(remote: str, expected: tuple[str, str] | None) -> None:
    assert github_slug(remote) == expected


class TestCommitEmailWarning:
    def test_warns_when_the_email_is_unset(self) -> None:
        warning = commit_email_warning(None, "you")

        assert warning is not None
        assert "user.email is not set" in warning

    @pytest.mark.parametrize(
        "email", ["123+other@users.noreply.github.com", "other@users.noreply.github.com"]
    )
    def test_warns_when_the_noreply_address_belongs_to_another_login(self, email: str) -> None:
        warning = commit_email_warning(email, "you")

        assert warning is not None
        assert "'other'" in warning

    @pytest.mark.parametrize(
        ("email", "login"),
        [
            ("123+You@users.noreply.github.com", "you"),
            ("you@example.com", "you"),
            ("123+other@users.noreply.github.com", None),
        ],
    )
    def test_accepts_a_matching_or_unverifiable_email(self, email: str, login: str | None) -> None:
        assert commit_email_warning(email, login) is None


class TestFetchIsFork:
    @pytest.mark.parametrize(("body", "expected"), [('{"fork": true}', True), ("{}", False)])
    def test_reads_the_fork_flag_of_the_public_api(self, serve, body: str, expected: bool) -> None:
        requested = serve(body)

        assert fetch_is_fork("you", "pixel-art") is expected
        assert requested == ["https://api.github.com/repos/you/pixel-art"]

    def test_is_unknown_when_offline(self) -> None:
        assert fetch_is_fork("you", "pixel-art") is None

    def test_is_unknown_for_a_reply_that_is_not_json(self, serve) -> None:
        serve("<html>rate limited</html>")

        assert fetch_is_fork("you", "pixel-art") is None


def test_profile_repo_url() -> None:
    assert profile_repo_url("octocat") == "https://github.com/octocat/octocat"


USER_NAME_SOURCE = "git user.name; set github.user to be sure"
SEARCH_SOURCE = "GitHub commit search by git user.email"


def search_result(*logins: str | None) -> str:
    items = [{"author": None if login is None else {"login": login}} for login in logins]
    return json.dumps({"total_count": len(items), "items": items})


@pytest.fixture
def commit_search(monkeypatch: pytest.MonkeyPatch):
    """Answer GitHub's commit search with ``body`` and record each request."""
    requests: list[tuple[urllib.request.Request, float]] = []

    def install(body: str) -> list[tuple[urllib.request.Request, float]]:
        def fake_urlopen(request: urllib.request.Request, timeout: float) -> FakeResponse:
            requests.append((request, timeout))
            return FakeResponse(body)

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        return requests

    return install


class TestDetectGithubUsername:
    def test_github_user_wins(self, set_global_git_config, fake_gh) -> None:
        set_global_git_config("github.user", "octocat")
        set_global_git_config("user.email", "1+other@users.noreply.github.com")
        fake_gh("echo someone-else")

        assert detect_github_username() == ("octocat", "git config github.user")

    @pytest.mark.parametrize(
        "email", ["123+octocat@users.noreply.github.com", "octocat@users.noreply.github.com"]
    )
    def test_falls_back_to_a_noreply_user_email(self, set_global_git_config, email: str) -> None:
        set_global_git_config("user.email", email)

        assert detect_github_username() == ("octocat", "the no-reply git user.email")

    def test_a_noreply_email_wins_over_user_name(self, set_global_git_config) -> None:
        set_global_git_config("user.name", "someone-else")
        set_global_git_config("user.email", "octocat@users.noreply.github.com")

        assert detect_github_username() == ("octocat", "the no-reply git user.email")

    def test_guesses_from_a_user_name_shaped_like_a_login(
        self, set_global_git_config, commit_search
    ) -> None:
        set_global_git_config("user.name", "octocat")
        set_global_git_config("user.email", "octocat@gmail.com")
        requests = commit_search(search_result("someone-else"))

        assert detect_github_username() == ("octocat", USER_NAME_SOURCE)
        assert requests == []

    @pytest.mark.parametrize("name", ["Octo Cat", "-octocat", "octocat-", "octo--cat", "a" * 40])
    def test_skips_a_user_name_that_is_not_a_login(
        self, set_global_git_config, commit_search, name: str
    ) -> None:
        set_global_git_config("user.name", name)
        set_global_git_config("user.email", "octocat@gmail.com")
        commit_search(search_result("octocat"))

        assert detect_github_username() == ("octocat", SEARCH_SOURCE)

    def test_searches_public_commits_by_user_email(
        self, set_global_git_config, commit_search
    ) -> None:
        set_global_git_config("user.name", "Octo Cat")
        set_global_git_config("user.email", "octo+cat@gmail.com")
        requests = commit_search(search_result("octocat", "someone-else"))

        assert detect_github_username() == ("octocat", SEARCH_SOURCE)
        [(request, timeout)] = requests
        assert request.full_url == (
            "https://api.github.com/search/commits?q=author-email%3Aocto%2Bcat%40gmail.com"
        )
        assert request.get_header("Authorization") is None
        assert request.get_header("User-agent")
        assert timeout <= 10

    @pytest.mark.parametrize(
        "body",
        [
            search_result(),
            search_result(None),
            search_result("not a login!"),
            "not json",
            json.dumps({"message": "API rate limit exceeded"}),
            json.dumps([]),
        ],
    )
    def test_the_commit_search_finds_nothing_in(
        self, set_global_git_config, commit_search, body: str
    ) -> None:
        set_global_git_config("user.email", "octocat@gmail.com")
        commit_search(body)

        assert detect_github_username() is None

    @pytest.mark.parametrize(
        "error",
        [
            urllib.error.HTTPError("url", 403, "rate limit exceeded", None, None),  # type: ignore[arg-type]
            urllib.error.URLError("offline"),
            TimeoutError("timed out"),
        ],
    )
    def test_the_commit_search_is_silent_on_failure(
        self, set_global_git_config, monkeypatch: pytest.MonkeyPatch, error: Exception
    ) -> None:
        set_global_git_config("user.email", "octocat@gmail.com")

        def failing_urlopen(*_args: object, **_kwargs: object) -> None:
            raise error

        monkeypatch.setattr("urllib.request.urlopen", failing_urlopen)

        assert detect_github_username() is None

    def test_skips_the_commit_search_without_a_user_email(
        self, set_global_git_config, commit_search
    ) -> None:
        set_global_git_config("user.name", "Octo Cat")
        requests = commit_search(search_result("octocat"))

        assert detect_github_username() is None
        assert requests == []

    def test_reads_the_settings_of_the_current_repository(
        self, git_repo: git.Repo, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        with git_repo.config_writer() as cw:
            cw.set_value("user", "name", "octocat")
        monkeypatch.chdir(str(git_repo.working_tree_dir))

        assert detect_github_username() == ("octocat", USER_NAME_SOURCE)

    def test_falls_back_to_gh_when_installed(self, set_global_git_config, fake_gh) -> None:
        set_global_git_config("user.email", "octocat@example.com")
        fake_gh("echo octocat")

        assert detect_github_username() == ("octocat", "gh api user")

    def test_skips_an_invalid_github_user(self, set_global_git_config) -> None:
        set_global_git_config("github.user", "not a login!")

        assert detect_github_username() is None

    def test_finds_nothing_without_settings_or_gh(self) -> None:
        assert detect_github_username() is None

    def test_ignores_gh_when_it_fails(self, fake_gh) -> None:
        fake_gh("echo 'not logged in' >&2; exit 1")

        assert detect_github_username() is None

    def test_gives_up_on_gh_after_a_timeout(self, fake_gh, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_gh("sleep 5; echo octocat")
        monkeypatch.setattr("github_pixel_artworks.github.GH_TIMEOUT_SECONDS", 0.2)

        assert detect_github_username() is None
