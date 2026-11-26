from datetime import date, datetime, timedelta
from pathlib import Path

import git
import pytest

from github_pixel_artworks.core import (
    calculate_multiplier,
    drawing_path,
    fetch_max_daily_commits,
    get_auto_start_date,
    get_first_sunday_of_year,
    grid_to_text,
    load_grid,
    normalize_github_https_url,
    preview,
    resolve_github_repo_url,
    save_grid,
)


def test_grid_to_text_and_save_roundtrip(tmp_path):
    grid = [
        [0, 1, 0],
        [2, 0, 1],
        [0, 0, 0],
        [1, 1, 1],
        [0, 0, 1],
        [1, 0, 0],
        [0, 1, 0],
    ]
    text = grid_to_text(grid)
    assert text.endswith("\n")
    assert text.splitlines()[0] == " * "
    assert text.splitlines()[1] == "* *"
    path = tmp_path / "nested" / "art.txt"
    save_grid(path, grid)
    loaded = load_grid(path)
    # save_grid collapses levels >0 to '*', so 2 becomes 1
    assert loaded[1][0] == 1
    assert loaded[0] == [0, 1, 0]


def test_get_first_sunday_of_year_is_sunday_in_january():
    start = get_first_sunday_of_year(2026)
    assert start.year == 2026
    assert start.month == 1
    assert start.weekday() == 6  # Sunday
    assert start.day <= 7


def test_get_auto_start_date_is_sunday():
    start = get_auto_start_date(offset_weeks=0, today=date(2026, 6, 15))
    assert start.weekday() == 6
    assert start.date() == date(2025, 6, 15)  # first Sunday on/after 2025-06-15
    assert get_auto_start_date(offset_weeks=2, today=date(2026, 6, 15)).date() == date(2025, 6, 29)


def test_calculate_multiplier():
    assert calculate_multiplier(0) == 1
    assert calculate_multiplier(-3) == 1
    assert calculate_multiplier(4) == 1
    assert calculate_multiplier(5) == 2
    assert calculate_multiplier(8) == 2
    assert calculate_multiplier(9) == 3


def test_preview_counts_commits_and_span():
    grid = [[1, 0], [0, 1], [0, 0], [0, 0], [0, 0], [0, 0], [0, 0]]
    start = datetime(2026, 1, 4)  # a Sunday
    text = preview(grid, start, multiplier=3)
    assert "Total weeks: 2" in text
    assert "Multiplier: 3" in text
    assert "Total commits that will be created: 6" in text
    assert "2026-01-04" in text


def test_fetch_max_daily_commits_parses_html(monkeypatch):
    html = """
    <tool-tip for="day-1">5 contributions on January 1st.</tool-tip>
    <tool-tip for="day-2">12 contributions on January 2nd.</tool-tip>
    <span>not a day</span>
    """

    class FakeResp:
        def read(self):
            return html.encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        "github_pixel_artworks.core.urllib.request.urlopen",
        lambda url, timeout=15: FakeResp(),
    )
    assert fetch_max_daily_commits("simonerigoni") == 12


def test_fetch_max_daily_commits_returns_none_on_error(monkeypatch):
    import urllib.error

    def _raise(*_args, **_kwargs):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr("github_pixel_artworks.core.urllib.request.urlopen", _raise)
    assert fetch_max_daily_commits("nobody") is None


# ---------------------------------------------------------------------------
# Regression tests from the code quality review
# ---------------------------------------------------------------------------

FIXTURES = Path(__file__).parent / "fixtures"


class _FakeResp:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResp:
        return self

    def __exit__(self, *args: object) -> bool:
        return False


def _serve(monkeypatch: pytest.MonkeyPatch, body: str) -> list[str]:
    calls: list[str] = []

    def fake_urlopen(url: str, timeout: float = 15) -> _FakeResp:
        calls.append(url)
        return _FakeResp(body.encode())

    monkeypatch.setattr("github_pixel_artworks.core.urllib.request.urlopen", fake_urlopen)
    return calls


def test_fetch_max_daily_commits_parses_real_github_markup(monkeypatch: pytest.MonkeyPatch):
    # Snippet of https://github.com/users/<name>/contributions as served in 2026:
    # the count lives in a <tool-tip> next to the <td data-date=...> cell.
    html = (FIXTURES / "contributions_snippet.html").read_text(encoding="utf-8")
    _serve(monkeypatch, html)
    assert fetch_max_daily_commits("simonerigoni") == 12


def test_fetch_max_daily_commits_handles_singular_and_thousands(monkeypatch: pytest.MonkeyPatch):
    html = (
        '<tool-tip for="a">1 contribution on May 1st.</tool-tip>\n'
        '<tool-tip for="b">1,234 contributions on May 2nd.</tool-tip>\n'
        '<tool-tip for="c">No contributions on May 3rd.</tool-tip>\n'
    )
    _serve(monkeypatch, html)
    assert fetch_max_daily_commits("someone") == 1234


@pytest.mark.parametrize("bad", ["", "../orgs/x", "a/b", "-dash", "a" * 40, "x?y=1"])
def test_fetch_max_daily_commits_rejects_invalid_usernames(monkeypatch: pytest.MonkeyPatch, bad):
    calls = _serve(monkeypatch, "")
    assert fetch_max_daily_commits(bad) is None
    assert calls == []


def test_get_auto_start_date_on_leap_day():
    # datetime(year - 1, 2, 29) used to raise ValueError on Feb 29.
    today = date(2028, 2, 29)
    start = get_auto_start_date(offset_weeks=0, today=today)
    assert start.weekday() == 6
    assert today - timedelta(days=365) <= start.date() < today - timedelta(days=358)


def test_load_grid_uses_widest_row_when_first_row_is_empty(tmp_path: Path):
    # Editors that strip trailing whitespace turn an all-empty top row into "".
    p = tmp_path / "art.txt"
    p.write_text("\n  * *\n *****\n *****\n  ***\n   *\n\n", encoding="utf-8")
    grid = load_grid(p)
    assert len(grid) == 7
    assert all(len(row) == 6 for row in grid)
    assert grid[1] == [0, 0, 1, 0, 1, 0]


def test_load_grid_ignores_non_ascii_digits(tmp_path: Path):
    p = tmp_path / "art.txt"
    p.write_text("\u00b2*\n" * 7, encoding="utf-8")  # superscript two
    assert load_grid(p)[0] == [0, 1]


def test_load_grid_reads_intensity_levels(tmp_path: Path):
    p = tmp_path / "art.txt"
    p.write_text("x*234#H\n" * 7, encoding="utf-8")
    assert load_grid(p)[0] == [0, 1, 2, 3, 4, 4, 4]


def test_load_grid_rejects_content_after_seventh_row(tmp_path: Path):
    p = tmp_path / "art.txt"
    p.write_text("*\n" * 8, encoding="utf-8")
    with pytest.raises(ValueError, match="7 rows"):
        load_grid(p)


def test_load_grid_allows_trailing_blank_lines(tmp_path: Path):
    p = tmp_path / "art.txt"
    p.write_text("*\n" * 7 + "\n\n", encoding="utf-8")
    assert len(load_grid(p)) == 7


def test_load_grid_rejects_fewer_than_seven_rows(tmp_path: Path):
    p = tmp_path / "art.txt"
    p.write_text("*\n" * 6, encoding="utf-8")
    with pytest.raises(ValueError, match="7 rows"):
        load_grid(p)


def test_load_grid_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_grid(tmp_path / "nope.txt")


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
def test_normalize_github_https_url(remote: str, expected: str | None):
    assert normalize_github_https_url(remote) == expected


def test_resolve_github_repo_url_falls_back_to_username(tmp_path: Path):
    repo = git.Repo.init(tmp_path / "r")
    assert resolve_github_repo_url(repo) is None
    assert (
        resolve_github_repo_url(repo, username="someone")
        == "https://github.com/someone/github_pixel_artworks"
    )


def test_drawing_path_stays_inside_data_dir(tmp_path: Path):
    assert drawing_path(tmp_path, "my_art") == tmp_path / "my_art.txt"
    assert drawing_path(tmp_path, " heart.txt ") == tmp_path / "heart.txt"
    assert drawing_path(tmp_path, "") == tmp_path / "untitled.txt"
    for bad in ["../evil", "sub/dir", "..", "C:\\temp\\x", "/etc/passwd"]:
        with pytest.raises(ValueError):
            drawing_path(tmp_path, bad)
