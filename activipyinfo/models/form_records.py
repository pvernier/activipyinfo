from __future__ import annotations

import builtins
import json
from collections.abc import Iterable, Mapping
from datetime import date
from typing import TYPE_CHECKING, Any

from .._pandas import is_missing
from ..ids import cuid
from ._common import one
from .fields import FormField, _SelectField
from .form_schema import FormSchema
from .record import Record, RecordHistoryEntry
from .values import encode_value, is_read_only

if TYPE_CHECKING:
    from ..services.records import RecordsService
    from .database import Form

__all__ = ["FormRecords"]

# Special keys of rows passed to add_many / update_many.
ID_KEY = "_id"
PARENT_KEY = "_parent"


class FormRecords:
    """The records of a form, as returned by ``form.records``.

    Values are given as dicts keyed by field code, id or label, with Python
    values: they are checked and converted using the form's schema (select
    labels become option ids, dates become ``YYYY-MM-DD``, ...).

    Example:
        >>> provinces.records.add({"pcode": "LBN001", "name": "Mount Lebanon"})
        >>> province = provinces.records.find(pcode="LBN001")
        >>> households.records.add({"province": province, "members": 5})
    """

    def __init__(self, form: Form) -> None:
        self._form = form
        self._schema: FormSchema | None = None

    def __repr__(self) -> str:
        return f"FormRecords({self._form!r})"

    @property
    def _records(self) -> RecordsService:
        service: RecordsService = self._form.database.client.records
        return service

    # -- Schema and value conversion ---------------------------------------

    def schema(self, *, refresh: bool = False) -> FormSchema:
        """The form's schema, fetched once and cached."""
        if self._schema is None or refresh:
            self._schema = self._form.schema()
        return self._schema

    def encode(self, values: Mapping[str, Any]) -> dict[str, Any]:
        """Convert ``{field: value}`` to API field values keyed by field id."""
        schema = self.schema()
        encoded: dict[str, Any] = {}
        for key, value in values.items():
            try:
                form_field = schema.field(key)
            except LookupError:
                raise KeyError(f"{self._form!r} has no field {key!r}") from None
            if is_missing(value):
                value = None
            encoded[form_field.id] = encode_value(form_field, value)
        return encoded

    def _parent_id(self, parent: Record | str | None) -> str | None:
        from .database import SubForm

        parent_id = parent.record_id if isinstance(parent, Record) else parent
        if isinstance(self._form, SubForm) and parent_id is None:
            raise ValueError(
                f"{self._form!r} is a subform: pass the parent record (parent=...)"
            )
        return parent_id

    def _change(
        self,
        record_id: str,
        values: Mapping[str, Any],
        *,
        parent: Record | str | None = None,
    ) -> dict[str, Any]:
        from ..services.records import change

        return change(
            self._form.id,
            record_id,
            self.encode(values),
            parent_record_id=parent.record_id if isinstance(parent, Record) else parent,
        )

    # -- Reading ---------------------------------------------------------

    def get(self, record: Record | str) -> Record:
        """Fetch a record by id."""
        return self._records.get(self._form.id, _record_id(record), self.schema())

    def exists(self, record: Record | str) -> bool:
        return self._records.exists(self._form.id, _record_id(record))

    def history(self, record: Record | str) -> builtins.list[RecordHistoryEntry]:
        """Every change made to a record, oldest first."""
        return self._records.history(self._form.id, _record_id(record))

    def list(
        self,
        *,
        filter: str | None = None,
        limit: int | None = None,
    ) -> builtins.list[Record]:
        """Fetch records (all of them by default) with every stored field.

        Args:
            filter: A boolean formula, e.g. ``"members > 5"``.
            limit: Maximum number of records.
        """
        schema = self.schema()
        stored = [f for f in schema.fields if not is_read_only(f)]
        columns = {ID_KEY: "_id", **{f.id: f.id for f in stored}}
        result = self._form.database.client.queries.columns(
            self._form.id, columns, filter=filter, limit=limit
        )
        records = []
        for row in result:
            fields = {k: v for k, v in row.items() if k != ID_KEY and v is not None}
            records.append(
                Record(
                    record_id=row[ID_KEY],
                    form_id=self._form.id,
                    fields=fields,
                    raw=row,
                    schema=schema,
                )
            )
        return records

    def find_all(self, **key_values: Any) -> builtins.list[str]:
        """Ids of the records whose fields equal the given values.

        Example: ``form.records.find_all(province="LBN001", status="Displaced")``
        """
        if not key_values:
            raise ValueError("Pass at least one field=value criterion")
        schema = self.schema()
        conditions = [
            f"{_formula_ref(schema.field(key))} == "
            f"{_formula_literal(schema.field(key), value)}"
            for key, value in key_values.items()
        ]
        result = self._form.database.client.queries.columns(
            self._form.id, {ID_KEY: "_id"}, filter=" && ".join(conditions)
        )
        return [row[ID_KEY] for row in result]

    def ref(self, **key_values: Any) -> str:
        """The id of the one record whose fields equal the given values.

        Useful to fill reference fields:
        ``households.records.add({"province": provinces.records.ref(pcode="LBN001")})``
        """
        criteria = ", ".join(f"{k}={v!r}" for k, v in key_values.items())
        return one(
            self.find_all(**key_values), f"record with {criteria} in {self._form!r}"
        )

    def find(self, **key_values: Any) -> Record:
        """The one record whose fields equal the given values."""
        return self.get(self.ref(**key_values))

    # -- Writing ---------------------------------------------------------

    def add(
        self,
        values: Mapping[str, Any] | None = None,
        *,
        record_id: str | None = None,
        parent: Record | str | None = None,
        **field_values: Any,
    ) -> Record:
        """Add a record and return it as saved by the server.

        Values can be passed as a dict or as keyword arguments (by code).
        ``parent`` is the parent record, for a record of a subform.
        """
        new_id = record_id or cuid()
        entry = self._change(
            new_id, {**(values or {}), **field_values}, parent=self._parent_id(parent)
        )
        self._records.submit([entry])
        return self.get(new_id)

    def add_many(
        self,
        rows: Iterable[Mapping[str, Any]] | Any,
        *,
        parent: Record | str | None = None,
        batch_size: int = 200,
    ) -> builtins.list[str]:
        """Add many records, in batches; returns their ids.

        Each row is a ``{field: value}`` dict, or ``rows`` is a
        :class:`pandas.DataFrame` whose columns are fields (missing values
        leave the field empty). The special key ``"_id"`` sets the record id,
        and ``"_parent"`` the parent record (subforms), which otherwise
        defaults to ``parent``.

        Raises:
            RecordBatchError: a batch failed; ``error.submitted`` lists the
                records that were added before it.
        """

        rows = _rows(rows)

        def changes() -> Iterable[dict[str, Any]]:
            for row in rows:
                fields = {k: v for k, v in row.items() if k not in (ID_KEY, PARENT_KEY)}
                yield self._change(
                    row.get(ID_KEY) or cuid(),
                    fields,
                    parent=self._parent_id(row.get(PARENT_KEY, parent)),
                )

        return self._records.submit(changes(), batch_size=batch_size)

    def update(
        self,
        record: Record | str,
        values: Mapping[str, Any] | None = None,
        **field_values: Any,
    ) -> Record:
        """Change some fields of a record and return it as saved.

        Fields not given keep their value; ``None`` clears a field.
        """
        record_id = _record_id(record)
        entry = self._change(record_id, {**(values or {}), **field_values})
        self._records.submit([entry])
        return self.get(record_id)

    def update_many(
        self, rows: Iterable[Mapping[str, Any]] | Any, *, batch_size: int = 200
    ) -> builtins.list[str]:
        """Update many records, in batches. Each row (dict or DataFrame row)
        needs an ``"_id"`` key."""
        rows = _rows(rows)

        def changes() -> Iterable[dict[str, Any]]:
            for row in rows:
                if not row.get(ID_KEY):
                    raise ValueError(f"Row without {ID_KEY!r}: {dict(row)!r}")
                fields = {k: v for k, v in row.items() if k != ID_KEY}
                yield self._change(row[ID_KEY], fields)

        return self._records.submit(changes(), batch_size=batch_size)

    def delete(self, record: Record | str) -> None:
        """Delete a record (it can be restored with :meth:`recover`)."""
        self.delete_many([record])

    def delete_many(
        self, records: Iterable[Record | str], *, batch_size: int = 200
    ) -> builtins.list[str]:
        """Delete many records, in batches."""
        from ..services.records import change

        return self._records.submit(
            (change(self._form.id, _record_id(r), deleted=True) for r in records),
            batch_size=batch_size,
        )

    def recover(self, record: Record | str) -> Record:
        """Restore a deleted record and return it."""
        record_id = _record_id(record)
        self._records.recover(self._form.id, record_id)
        return self.get(record_id)


def _rows(rows: Any) -> Iterable[Mapping[str, Any]]:
    """Rows from dicts or from a pandas DataFrame."""
    if hasattr(rows, "to_dict") and hasattr(rows, "columns"):
        records: builtins.list[Mapping[str, Any]] = rows.to_dict("records")
        return records
    iterable: Iterable[Mapping[str, Any]] = rows
    return iterable


def _record_id(record: Record | str) -> str:
    return record.record_id if isinstance(record, Record) else record


def _formula_ref(form_field: FormField) -> str:
    return form_field.code or form_field.id


def _formula_literal(form_field: FormField, value: Any) -> str:
    """Write ``value`` as a formula literal for comparisons with ``form_field``."""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(form_field, _SelectField):
        value = form_field.option(value).label  # formulas compare option labels
    elif isinstance(value, date):
        value = value.isoformat()
    elif isinstance(value, Record):
        value = value.record_id
    return json.dumps(str(value))
