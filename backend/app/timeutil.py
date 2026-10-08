"""Shanghai dates and UTC timestamps."""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo('Asia/Shanghai')


def now_utc() -> datetime:
    """Return the current timezone-aware UTC time."""
    return datetime.now(timezone.utc)


def iso_utc(moment: datetime | None = None) -> str:
    """Format a UTC timestamp that sorts as text."""
    value = moment or now_utc()
    return value.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def today_shanghai() -> date:
    """Return today's date in Asia/Shanghai."""
    return datetime.now(SHANGHAI).date()


def month_start(day: date | None = None) -> date:
    """Return the first day of the Shanghai month containing day."""
    current = day or today_shanghai()
    return current.replace(day=1)


def plus_days(day: date, days: int) -> date:
    """Return day shifted by a number of calendar days."""
    return day + timedelta(days=days)
