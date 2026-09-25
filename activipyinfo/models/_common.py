from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime
from typing import Any

from ..exceptions import MultipleMatchesError, NoMatchError


def ms_to_datetime(value: Any) -> datetime | None:
    """Convert milliseconds since the epoch (as sent by the API) to a UTC datetime."""
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000, tz=UTC)


def parse_time(value: Any) -> datetime | date | None:
    """Parse a timestamp as sent by the API.

    Accepts epoch numbers in milliseconds or seconds (the API uses both) and
    ISO 8601 date or date-time strings. Returns None for missing values.
    """
    if value is None or value == "":
        return None
    if isinstance(value, int | float):
        # Anything past ~5000 AD in seconds is really milliseconds.
        seconds = value / 1000 if abs(value) > 1e11 else value
        return datetime.fromtimestamp(seconds, tz=UTC)
    if isinstance(value, str):
        try:
            if len(value) == 10:
                return date.fromisoformat(value)
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def one[T](matches: Iterable[T], description: str) -> T:
    """Return the single item of ``matches``, or raise a lookup error."""
    found = list(matches)
    if not found:
        raise NoMatchError(f"No {description}")
    if len(found) > 1:
        listing = ", ".join(repr(item) for item in found)
        raise MultipleMatchesError(
            f"{len(found)} matches for {description}: {listing}. Use the id instead."
        )
    return found[0]
