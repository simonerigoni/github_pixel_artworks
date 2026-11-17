from datetime import datetime

from github_pixel_artworks.core import (
    calculate_multiplier,
    fetch_max_daily_commits,
    get_auto_start_date,
    get_first_sunday_of_year,
    grid_to_text,
    load_grid,
    preview,
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


def test_get_auto_start_date_is_sunday(monkeypatch):
    class FakeDate(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 6, 15, 9, 0, 0)

    monkeypatch.setattr("github_pixel_artworks.core.datetime", FakeDate)
    start = get_auto_start_date(offset_weeks=0)
    assert start.weekday() == 6


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
    <div data-date="2026-01-01">5 contributions</div>
    <div data-date="2026-01-02">12 contributions</div>
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
