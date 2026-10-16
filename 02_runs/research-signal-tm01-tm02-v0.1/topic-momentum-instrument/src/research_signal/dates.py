from __future__ import annotations

import calendar
from datetime import date
from typing import Iterator


def month_end(day: date) -> date:
    return date(day.year, day.month, calendar.monthrange(day.year, day.month)[1])


def add_months(day: date, months: int) -> date:
    """Shift a date by whole months, clamping the day when necessary."""
    zero_based = day.year * 12 + day.month - 1 + months
    year, month_index = divmod(zero_based, 12)
    month = month_index + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def month_distance(start: date, end: date) -> int:
    """Return the number of month boundaries from start to end."""
    return (end.year - start.year) * 12 + end.month - start.month


def iter_month_buckets(start: date, end: date) -> Iterator[tuple[date, date, bool]]:
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        natural_end = month_end(cursor)
        bucket_start = max(cursor, start)
        bucket_end = min(natural_end, end)
        is_complete = bucket_start == cursor and bucket_end == natural_end
        yield bucket_start, bucket_end, is_complete
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
