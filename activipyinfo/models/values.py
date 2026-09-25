"""Conversion between Python values and ActivityInfo record field values.

Writing (``encode_value``) follows the formats documented by the R package:
dates as ``YYYY-MM-DD``, months as ``YYYY-MM``, weeks as ``YYYYWn``, select
options by id, references by record id and points as
``{"latitude": ..., "longitude": ...}``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime
from numbers import Integral, Real
from typing import Any

from .fields import (
    CalculatedField,
    DateField,
    FormField,
    FortnightField,
    GeoPointField,
    MonthField,
    MultiReferenceField,
    MultiSelectField,
    NoteField,
    QuantityField,
    ReferenceField,
    ReverseReferenceField,
    SectionHeader,
    SelectOption,
    SerialNumberField,
    SingleSelectField,
    SubformField,
    WeekField,
    _SelectField,
)

__all__ = ["decode_value", "encode_value", "is_read_only"]

_READ_ONLY = (
    CalculatedField,
    SerialNumberField,
    SectionHeader,
    NoteField,
    SubformField,
    ReverseReferenceField,
)


def is_read_only(field: FormField) -> bool:
    """Whether the field's value is computed, generated or not stored."""
    return isinstance(field, _READ_ONLY)


def encode_value(field: FormField, value: Any) -> Any:
    """Convert a Python value to the API representation for ``field``.

    ``None`` clears the field. Raises ``ValueError`` or ``TypeError`` for
    values the field cannot hold.
    """
    if is_read_only(field):
        raise ValueError(f"{field!r} is read-only")
    if value is None:
        return None
    if isinstance(field, DateField):
        return _encode_date(field, value)
    if isinstance(field, MonthField):
        if isinstance(value, date):
            return f"{value.year:04d}-{value.month:02d}"
        return _expect_str(field, value)
    if isinstance(field, WeekField | FortnightField):
        if isinstance(value, date):
            raise TypeError(
                f"{field!r} uses epidemiological weeks: pass a string such as "
                "'2024W7' rather than a date"
            )
        return _expect_str(field, value)
    if isinstance(field, QuantityField):
        if _is_bool(value) or not isinstance(value, Real):
            raise TypeError(f"{field!r} expects a number, got {value!r}")
        # Plain int/float: numpy numbers are not JSON serializable.
        return int(value) if isinstance(value, Integral) else float(value)
    if isinstance(field, SingleSelectField):
        return _option_id(field, value)
    if isinstance(field, MultiSelectField):
        values = [value] if isinstance(value, str | SelectOption) else value
        return [_option_id(field, v) for v in values]
    if isinstance(field, ReferenceField):
        return _record_id(value)
    if isinstance(field, MultiReferenceField):
        values = [value] if isinstance(value, str) else value
        return [_record_id(v) for v in values]
    if isinstance(field, GeoPointField):
        return _encode_point(field, value)
    return value


def decode_value(field: FormField, value: Any) -> Any:
    """Convert a value read from the API to a Python value for ``field``.

    Dates become :class:`datetime.date`, select option ids become labels and
    references (``"formId:recordId"``) become record ids. Other values are
    returned unchanged.
    """
    if value is None:
        return None
    if isinstance(field, DateField) and isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return value
    if isinstance(field, SingleSelectField):
        return _option_label(field, value)
    if isinstance(field, MultiSelectField) and isinstance(value, list):
        return [_option_label(field, v) for v in value]
    if isinstance(field, ReferenceField):
        return _strip_form_id(value)
    if isinstance(field, MultiReferenceField) and isinstance(value, list):
        return [_strip_form_id(v) for v in value]
    return value


# ----------------------------------------------------------------------


def _expect_str(field: FormField, value: Any) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field!r} expects a string, got {value!r}")
    return value


def _encode_date(field: FormField, value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = _expect_str(field, value)
    try:
        date.fromisoformat(text)
    except ValueError:
        raise ValueError(f"{field!r} expects a YYYY-MM-DD date, got {text!r}") from None
    return text


def _is_bool(value: Any) -> bool:
    # numpy booleans: numpy.bool_ (numpy 1) or numpy.bool (numpy 2)
    kind = type(value)
    return isinstance(value, bool) or (
        kind.__module__ == "numpy" and kind.__name__ in ("bool_", "bool")
    )


def _option_id(field: _SelectField, value: Any) -> str:
    if isinstance(value, SelectOption):
        value = value.id
    elif _is_bool(value):
        value = str(bool(value))  # e.g. options "True"/"False" from from_data()
    try:
        return field.option(value).id
    except KeyError:
        labels = [o.label for o in field.options]
        raise ValueError(
            f"{value!r} is not an option of {field!r}; options: {labels}"
        ) from None


def _option_label(field: _SelectField, value: Any) -> Any:
    try:
        return field.option(value).label
    except KeyError:
        return value


def _record_id(value: Any) -> str:
    record_id = getattr(value, "record_id", value)
    if not isinstance(record_id, str):
        raise TypeError(f"Expected a record id or a Record, got {value!r}")
    return record_id


def _strip_form_id(value: Any) -> Any:
    if isinstance(value, str) and ":" in value:
        return value.split(":", 1)[1]
    return value


def _encode_point(field: FormField, value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        if "latitude" not in value or "longitude" not in value:
            raise ValueError(f"{field!r} expects latitude and longitude")
        return dict(value)
    if isinstance(value, Iterable) and not isinstance(value, str):
        items = list(value)
        if len(items) in (2, 3):
            point = {"latitude": items[0], "longitude": items[1]}
            if len(items) == 3:
                point["accuracy"] = items[2]
            return point
    raise TypeError(
        f"{field!r} expects (latitude, longitude[, accuracy]) or a dict, got {value!r}"
    )
