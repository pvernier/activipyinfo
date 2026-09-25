from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from ._common import parse_time
from .form_schema import FormSchema
from .values import decode_value

__all__ = ["QueryResult", "Record", "RecordHistoryEntry"]


@dataclass(eq=False)
class Record:
    """A record of a form.

    ``fields`` holds the raw values keyed by field id, as sent by the API.
    When the record comes with its form's schema, values can be read by
    field code, id or label, converted to Python values (dates, option
    labels, referenced record ids)::

        record["pcode"]
        record.to_dict()   # {"pcode": ..., "name": ...}
    """

    record_id: str
    form_id: str
    fields: dict[str, Any] = field(default_factory=dict)
    parent_record_id: str | None = None
    last_edit_time: datetime | date | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    schema: FormSchema | None = field(default=None, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any], schema: FormSchema | None = None) -> Record:
        return cls(
            record_id=data["recordId"],
            form_id=data.get("formId", schema.id if schema else ""),
            fields=dict(data.get("fields") or {}),
            parent_record_id=data.get("parentRecordId"),
            last_edit_time=parse_time(data.get("lastEditTime")),
            raw=data,
            schema=schema,
        )

    def __repr__(self) -> str:
        return f"Record(record_id={self.record_id!r}, form_id={self.form_id!r})"

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, Record)
            and other.record_id == self.record_id
            and other.form_id == self.form_id
        )

    def __hash__(self) -> int:
        return hash((self.form_id, self.record_id))

    def _schema(self) -> FormSchema:
        if self.schema is None:
            raise ValueError(
                f"{self!r} has no schema: read values by field id in record.fields"
            )
        return self.schema

    def __getitem__(self, key: str) -> Any:
        """The value of a field (by code, id or label), as a Python value."""
        if self.schema is None:
            return self.fields[key]
        form_field = self.schema.field(key)
        return decode_value(form_field, self.fields.get(form_field.id))

    def get(self, key: str, default: Any = None) -> Any:
        try:
            value = self[key]
        except (KeyError, LookupError):
            return default
        return default if value is None else value

    def __iter__(self) -> Iterator[str]:
        return iter(self.to_dict())

    def to_dict(self, keys: str = "code") -> dict[str, Any]:
        """Values keyed by field ``"code"`` (id when a field has none), ``"id"``
        or ``"label"``, decoded to Python values. Fields without a value in
        this record are left out.
        """
        if keys not in ("code", "id", "label"):
            raise ValueError("keys must be 'code', 'id' or 'label'")
        schema = self._schema()
        values: dict[str, Any] = {}
        for form_field in schema.fields:
            if form_field.id not in self.fields:
                continue
            if keys == "code":
                name = form_field.code or form_field.id
            elif keys == "id":
                name = form_field.id
            else:
                name = form_field.label
            values[name] = decode_value(form_field, self.fields[form_field.id])
        return values


@dataclass
class RecordHistoryEntry:
    """One change in the history of a record."""

    time: datetime | date | None
    change_type: str | None = None
    version: int | None = None
    user_name: str | None = None
    user_email: str | None = None
    values: list[dict[str, Any]] = field(default_factory=list)
    sub_field_id: str | None = None
    sub_field_label: str | None = None
    sub_record_key: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> RecordHistoryEntry:
        user = data.get("user") or {}
        return cls(
            time=parse_time(data.get("time")),
            change_type=data.get("changeType"),
            version=data.get("version"),
            user_name=user.get("name"),
            user_email=user.get("email"),
            values=list(data.get("values") or []),
            sub_field_id=data.get("subFieldId"),
            sub_field_label=data.get("subFieldLabel"),
            sub_record_key=data.get("subRecordKey"),
            raw=data,
        )


@dataclass
class QueryResult:
    """Rows returned by a column query, plus paging information."""

    rows: list[dict[str, Any]]
    total_rows: int | None = None
    offset: int = 0

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self.rows)

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> dict[str, Any]:
        return self.rows[index]

    @classmethod
    def from_api(
        cls, data: dict[str, Any], column_ids: list[str] | None = None
    ) -> QueryResult:
        """Turn the API's column-oriented result into a list of row dicts.

        Each column is stored as ``array`` (one value per row), ``constant``
        (the same value for every row) or ``empty`` (no value).
        """
        n_rows = int(data.get("rows") or 0)
        columns: dict[str, Any] = data.get("columns") or {}
        values: dict[str, list[Any]] = {}
        for column_id, column in columns.items():
            storage = column.get("storage")
            if storage == "array":
                column_values = list(column.get("values") or [])
            elif storage == "constant":
                column_values = [column.get("value")] * n_rows
            elif storage == "empty":
                column_values = [None] * n_rows
            else:
                raise ValueError(
                    f"Unknown column storage {storage!r} for {column_id!r}"
                )
            if len(column_values) != n_rows:
                raise ValueError(
                    f"Column {column_id!r} has {len(column_values)} values "
                    f"for {n_rows} rows"
                )
            values[column_id] = column_values
        order = column_ids or list(values)
        rows = [
            {
                column_id: values.get(column_id, [None] * n_rows)[i]
                for column_id in order
            }
            for i in range(n_rows)
        ]
        return cls(
            rows=rows, total_rows=data.get("totalRows"), offset=data.get("offset") or 0
        )
