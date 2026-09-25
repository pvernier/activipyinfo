"""Guess a form schema from data, like the R package's
``createFormSchemaFromData()``."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from numbers import Real
from typing import Any

from .._pandas import is_missing
from .fields import (
    DateField,
    FormField,
    MultilineField,
    QuantityField,
    SelectOption,
    SingleSelectField,
    TextField,
)
from .form_schema import FormSchema

__all__ = ["schema_from_data"]

MAX_TEXT_LENGTH = 1024


def schema_from_data(
    data: Any,
    label: str,
    *,
    keys: Sequence[str] = (),
    required: Sequence[str] | None = None,
    codes: bool = True,
    bool_labels: tuple[str, str] = ("True", "False"),
) -> FormSchema:
    """Build a form schema with one field per column of ``data``.

    Args:
        data: A :class:`pandas.DataFrame`, or an iterable of dicts.
        label: The form's label.
        keys: Columns that form the key (they become required).
        required: Columns that are required (default: the keys).
        codes: Derive field codes from column names.
        bool_labels: Option labels for boolean columns (true, false).

    Field types: categorical and boolean columns become single selects,
    numbers quantities, dates (and date-times) dates, text single-line text,
    or multi-line text when a value has a line break or is longer than 1024
    characters.
    """
    columns, categories = _columns(data)
    required_columns = set(keys if required is None else required) | set(keys)
    unknown = (set(keys) | required_columns) - set(columns)
    if unknown:
        raise ValueError(f"Unknown columns: {sorted(unknown)}")

    used_codes: set[str] = set()
    fields: list[FormField] = []
    for name, values in columns.items():
        code = _unique_code(name, used_codes) if codes else None
        options = {
            "code": code,
            "key": name in keys,
            "required": name in required_columns,
        }
        fields.append(
            _infer_field(name, values, categories.get(name), bool_labels, options)
        )
    return FormSchema(label, fields)


def _columns(data: Any) -> tuple[dict[str, list[Any]], dict[str, list[str]]]:
    if hasattr(data, "columns") and hasattr(data, "dtypes"):  # a DataFrame
        columns: dict[str, list[Any]] = {}
        categories: dict[str, list[str]] = {}
        for name in data.columns:
            series = data[name]
            if str(series.dtype) == "category":
                categories[str(name)] = [str(c) for c in series.cat.categories]
            columns[str(name)] = series.tolist()
        return columns, categories

    rows: list[Mapping[str, Any]] = list(data)
    names: dict[str, None] = {}
    for row in rows:
        names.update(dict.fromkeys(row))
    return {name: [row.get(name) for row in rows] for name in names}, {}


def _infer_field(
    name: str,
    values: Iterable[Any],
    categories: list[str] | None,
    bool_labels: tuple[str, str],
    options: dict[str, Any],
) -> FormField:
    present = [v for v in values if not is_missing(v)]
    if categories is not None:
        return SingleSelectField(name, [SelectOption(c) for c in categories], **options)
    if present and all(_is_bool(v) for v in present):
        return SingleSelectField(
            name, [SelectOption(b) for b in bool_labels], **options
        )
    if present and all(isinstance(v, Real) for v in present):
        return _field(QuantityField, name, options)
    if present and all(isinstance(v, date) for v in present):
        return DateField(name, **options)
    text = [str(v) for v in present]
    if any("\n" in t or "\r" in t or len(t) > MAX_TEXT_LENGTH for t in text):
        return _field(MultilineField, name, options)
    return TextField(name, **options)


def _field(klass: type[FormField], name: str, options: dict[str, Any]) -> FormField:
    if options["key"]:
        raise ValueError(
            f"Column {name!r} cannot be a key: it would be a {klass.__name__}"
        )
    return klass(name, **options)


def _is_bool(value: Any) -> bool:
    # numpy booleans: numpy.bool_ (numpy 1) or numpy.bool (numpy 2)
    kind = type(value)
    return isinstance(value, bool) or (
        kind.__module__ == "numpy" and kind.__name__ in ("bool_", "bool")
    )


def _unique_code(name: str, used: set[str]) -> str | None:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    code = re.sub(r"[^A-Za-z0-9]+", "_", ascii_name).strip("_")
    code = re.sub(r"^[^A-Za-z]+", "", code)[:32].rstrip("_")
    if not code:
        return None
    candidate, n = code, 2
    while candidate.lower() in used:
        suffix = f"_{n}"
        candidate, n = code[: 32 - len(suffix)] + suffix, n + 1
    used.add(candidate.lower())
    return candidate
