"""Pure ledger and schedule rules."""

from datetime import date

LOW_BALANCE_THRESHOLD = 3


def balance_parts(total: int, opening: int, consumed: int) -> dict[str, int]:
    """Return used and remaining units.

    Remaining is purchased units minus opening use minus active
    check-in consumption. Used is defined so used + remaining = total.
    """
    remaining = total - opening - consumed
    return {
        'total_units': total,
        'used_units': total - remaining,
        'remaining_units': remaining,
    }


def is_low(remaining: int) -> bool:
    """Return whether the package should show the low-balance hint."""
    return remaining <= LOW_BALANCE_THRESHOLD


def units_for(status: str, charge: bool) -> int:
    """Return units consumed by one attendance fact."""
    if status == 'attended':
        return 1
    if status == 'leave' and charge:
        return 1
    return 0


def planned_key(course_id: int, local_date: str, local_time: str) -> str:
    """Return the idempotency key of a timetable slot."""
    return f'plan:{course_id}:{local_date}:{local_time}'


def schedule_covers(
    weekday: int,
    effective_from: str,
    effective_to: str | None,
    day: date,
) -> bool:
    """Return whether a weekly slot occurs on day."""
    if day.weekday() != weekday:
        return False
    iso = day.isoformat()
    if iso < effective_from:
        return False
    if effective_to is not None and iso > effective_to:
        return False
    return True


def ranges_overlap(
    left_from: str,
    left_to: str | None,
    right_from: str,
    right_to: str | None,
) -> bool:
    """Return whether two inclusive date ranges overlap."""
    left_end = left_to or '9999-12-31'
    right_end = right_to or '9999-12-31'
    return left_from <= right_end and right_from <= left_end
