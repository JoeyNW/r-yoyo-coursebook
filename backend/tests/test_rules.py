"""Balance identity."""

from app.services.rules import balance_parts


def test_used_plus_remaining_equals_total() -> None:
    parts = balance_parts(10, 3, 2)
    assert parts['remaining_units'] == 5
    assert parts['used_units'] == 5
    assert parts['used_units'] + parts['remaining_units'] == 10
