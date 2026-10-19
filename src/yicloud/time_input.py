"""Exact, timezone-aware timestamps for historical log queries."""

import re
from datetime import datetime, timezone

from .errors import InputError


def timestamp_ns(value):
    if value is None or type(value) is int:
        return value
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    match = re.fullmatch(
        r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})",
        value,
    )
    if not match:
        raise InputError(
            "Time requires Unix nanoseconds or RFC3339 with timezone (up to 9 decimals)"
        )
    base, fraction, offset = match.groups()
    try:
        if offset != "Z" and (int(offset[1:3]) > 23 or int(offset[4:]) > 59):
            raise ValueError()
        dt = datetime.fromisoformat(base + ("+00:00" if offset == "Z" else offset))
    except ValueError as e:
        raise InputError("Invalid RFC3339 timestamp") from e
    try:
        delta = dt.astimezone(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)
    except OverflowError as e:
        raise InputError("RFC3339 timestamp is outside the supported UTC datetime range") from e
    return (delta.days * 86400 + delta.seconds) * 10**9 + int((fraction or "").ljust(9, "0"))


def duration_ns(value):
    match = re.fullmatch(r"([1-9]\d*)(s|m|h|d)", value)
    if not match:
        raise InputError("--since requires a positive whole duration, e.g. 30s, 15m, 2h, 1d")
    number, unit = match.groups()
    return int(number) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit] * 10**9
