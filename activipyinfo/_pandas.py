"""Optional pandas support (``pip install "activipyinfo[pandas]"``)."""

from __future__ import annotations

import math
import sys
from typing import Any


def require_pandas() -> Any:
    """Import pandas, or explain how to install it."""
    try:
        import pandas
    except ImportError:
        raise ImportError(
            "This feature needs pandas: pip install 'activipyinfo[pandas]'"
        ) from None
    return pandas


def is_missing(value: Any) -> bool:
    """True for None, NaN, NaT and pandas.NA."""
    if value is None:
        return True
    if isinstance(value, float):
        return math.isnan(value)
    # Only pandas creates pandas.NA / NaT: no need to import it otherwise.
    pandas = sys.modules.get("pandas")
    if pandas is None:
        return False
    try:
        return bool(pandas.isna(value))
    except (TypeError, ValueError):  # list-like values
        return False
