"""Calendar helpers."""

from datetime import UTC, date, datetime, timedelta

from github_pixel_artworks.dates import (
    SUNDAY,
    get_auto_start_date,
    get_first_sunday_of_year,
    next_sunday,
    pixel_timestamp,
)


def test_next_sunday_keeps_a_sunday_and_moves_other_days_forward() -> None:
    assert next_sunday(date(2026, 1, 4)) == date(2026, 1, 4)
    assert next_sunday(date(2026, 1, 5)) == date(2026, 1, 11)


def test_first_sunday_of_year_is_in_the_first_week_of_january() -> None:
    start = get_first_sunday_of_year(2026)

    assert start == datetime(2026, 1, 4)
    assert start.weekday() == SUNDAY


def test_auto_start_date_is_first_sunday_a_year_ago() -> None:
    start = get_auto_start_date(offset_weeks=0, today=date(2026, 6, 15))

    assert start == datetime(2025, 6, 15)  # 2025-06-15 is a Sunday


def test_auto_start_date_applies_the_offset() -> None:
    start = get_auto_start_date(offset_weeks=2, today=date(2026, 6, 15))

    assert start == datetime(2025, 6, 29)


def test_auto_start_date_works_on_a_leap_day() -> None:
    today = date(2028, 2, 29)

    start = get_auto_start_date(today=today)

    assert start.weekday() == SUNDAY
    assert today - timedelta(days=365) <= start.date() < today - timedelta(days=358)


def test_pixel_timestamp_is_noon_utc_on_the_pixel_day() -> None:
    start = datetime(2026, 1, 4, 23, 30)  # the time of day is ignored

    when = pixel_timestamp(start, week=1, day=2)

    assert when == datetime(2026, 1, 13, 12, tzinfo=UTC)
