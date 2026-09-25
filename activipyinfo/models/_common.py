from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, TypeVar

from ..exceptions import MultipleMatchesError, NoMatchError

T = TypeVar("T")


def ms_to_datetime(value: Any) -> datetime | None:
    """Convert milliseconds since the epoch (as sent by the API) to a UTC datetime."""
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000, tz=UTC)


def one(matches: Iterable[T], description: str) -> T:
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
