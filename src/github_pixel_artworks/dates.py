"""Calendar helpers that place artwork columns on GitHub's weekly contribution grid."""

from datetime import UTC, date, datetime, timedelta

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


def next_sunday(day: date) -> date:
    """Return ``day`` if it is a Sunday, otherwise the following Sunday."""
    return day + timedelta(days=(SUNDAY - day.weekday()) % 7)


def get_first_sunday_of_year(year: int) -> datetime:
    """Return midnight of the first Sunday of ``year``: the left edge for that year's art."""
    first = next_sunday(date(year, 1, 1))
    return datetime(first.year, first.month, first.day)


def get_auto_start_date(offset_weeks: int = 0, today: date | None = None) -> datetime:
    """Return the Sunday that starts the profile's visible one-year window.

    That is the first Sunday on or after ``today - 365 days`` (``today`` defaults
    to the local date), shifted right by ``offset_weeks``.
    """
    start = next_sunday((today or date.today()) - timedelta(days=DAYS_PER_YEAR))
    return datetime(start.year, start.month, start.day) + timedelta(weeks=offset_weeks)


def pixel_timestamp(start: datetime, week: int, day: int) -> datetime:
    """Return the commit time for the pixel at column ``week``, row ``day``."""
    pixel_day = start.date() + timedelta(weeks=week, days=day)
    return datetime(pixel_day.year, pixel_day.month, pixel_day.day, COMMIT_HOUR_UTC, tzinfo=UTC)
