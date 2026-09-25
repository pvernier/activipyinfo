"""Lazy queries over a form's records.

Modelled on the R package's ``getRecords() |> filter() |> select() |>
collect()``: a :class:`Table` only describes the query; the records are
fetched by :meth:`Table.collect`, :meth:`Table.to_pandas` or iteration.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Literal

from .fields import (
    FormField,
    NoteField,
    ReferenceField,
    ReverseReferenceField,
    SectionHeader,
    SubformField,
)
from .form_records import _formula_literal, _formula_ref
from .form_schema import FormSchema
from .values import decode_value

if TYPE_CHECKING:
    from .database import Form

__all__ = ["Table", "default_columns"]

ColumnNames = Literal["label", "code", "id"]
ID_COLUMN = "_id"
PARENT_COLUMN = "_parent"

# Fields without a value of their own.
_NOT_QUERYABLE = (SectionHeader, NoteField, SubformField, ReverseReferenceField)


def _name(form_field: FormField, names: ColumnNames) -> str:
    if names == "label":
        return form_field.label
    if names == "code":
        return form_field.code or form_field.id
    return form_field.id


def default_columns(
    schema: FormSchema,
    related: Mapping[str, FormSchema] | None = None,
    *,
    names: ColumnNames = "label",
) -> dict[str, tuple[str, FormField | None]]:
    """The default columns of a form's table, like the R package's
    ``prettyColumns()``.

    Returns ``{column name: (formula, field)}``: the record id, the parent
    record id for a subform, then one column per field with a value. A
    reference field is replaced by the key fields of the form it references
    (``"Province P-code"``, formula ``<reference id>.<key id>``), or kept as
    the referenced record id when those keys are unknown.
    """
    related = related or {}
    columns: dict[str, tuple[str, FormField | None]] = {ID_COLUMN: ("_id", None)}
    if schema.parent_form_id:
        columns[PARENT_COLUMN] = ("@parent", None)

    def add(name: str, formula: str, form_field: FormField | None) -> None:
        unique, n = name, 2
        while unique in columns:
            unique, n = f"{name} ({n})", n + 1
        columns[unique] = (formula, form_field)

    separator = " " if names == "label" else "."
    for form_field in schema.fields:
        if isinstance(form_field, _NOT_QUERYABLE):
            continue
        referenced = (
            related.get(form_field.form_id)
            if isinstance(form_field, ReferenceField)
            else None
        )
        keys = referenced.key_fields if referenced else []
        if not keys:
            add(_name(form_field, names), form_field.id, form_field)
            continue
        for key in keys:
            add(
                f"{_name(form_field, names)}{separator}{_name(key, names)}",
                f"{form_field.id}.{key.id}",
                key,
            )
    return columns


@dataclass(frozen=True)
class Table:
    """A query over a form's records: columns, filters, sort order and window.

    Every method returns a new table; nothing is fetched until
    :meth:`collect`, :meth:`first`, :meth:`count`, :meth:`to_pandas` or
    iteration.

    Example:
        >>> (households.table()
        ...     .select("head", "members", province="province.name")
        ...     .where(status="Displaced")
        ...     .filter("members > 5")
        ...     .sort("members", desc=True)
        ...     .limit(10)
        ...     .to_pandas())
    """

    form: Form
    names: ColumnNames = "label"
    selected: tuple[tuple[str, str], ...] | None = None
    filters: tuple[str, ...] = ()
    order: tuple[tuple[str, str], ...] = ()
    skip: int = 0
    max_rows: int | None = None
    _state: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    def __repr__(self) -> str:
        parts = [f"{self.form!r}"]
        if self.selected is not None:
            parts.append(f"columns={[name for name, _ in self.selected]}")
        if self.filters:
            parts.append(f"filter={self.filter_formula!r}")
        if self.order:
            parts.append(f"sort={list(self.order)}")
        if self.skip:
            parts.append(f"offset={self.skip}")
        if self.max_rows is not None:
            parts.append(f"limit={self.max_rows}")
        return f"Table({', '.join(parts)})"

    # -- Schemas (fetched once per table chain) ------------------------------

    def _schema(self) -> FormSchema:
        if "schema" not in self._state:
            self._state["schema"] = self.form.records.schema()
        schema: FormSchema = self._state["schema"]
        return schema

    def _related(self) -> dict[str, FormSchema]:
        if "related" not in self._state:
            has_references = any(
                isinstance(f, ReferenceField) for f in self._schema().fields
            )
            self._state["related"] = (
                self.form.database.client.forms.tree(self.form.id)
                if has_references
                else {}
            )
        related: dict[str, FormSchema] = self._state["related"]
        return related

    def _copy(self, **changes: Any) -> Table:
        # Share the cached schemas with the new table.
        return replace(self, _state=self._state, **changes)

    # -- Building the query ------------------------------------------------

    def select(self, *fields: str, with_id: bool = True, **formulas: str) -> Table:
        """Choose the columns.

        Positional arguments are fields (code, id or label) or formulas,
        named after themselves; keyword arguments name a formula:
        ``select("head", province="province.name")``. The record id column
        ``"_id"`` comes first unless ``with_id=False``.
        """
        columns: list[tuple[str, str]] = [(ID_COLUMN, "_id")] if with_id else []
        columns += [(name, self._formula(name)) for name in fields]
        columns += [
            (name, self._formula(formula)) for name, formula in formulas.items()
        ]
        return self._copy(selected=tuple(columns))

    def filter(self, formula: str) -> Table:
        """Keep the records for which the formula is true (combined with AND)."""
        return self._copy(filters=(*self.filters, f"({formula})"))

    def where(self, **field_values: Any) -> Table:
        """Keep the records whose fields equal the given values."""
        schema = self._schema()
        conditions = tuple(
            f"{_formula_ref(schema.field(key))} == "
            f"{_formula_literal(schema.field(key), value)}"
            for key, value in field_values.items()
        )
        return self._copy(filters=(*self.filters, *conditions))

    def sort(self, *keys: str, desc: bool = False) -> Table:
        """Sort by fields or formulas (after any earlier sort keys)."""
        direction = "DESC" if desc else "ASC"
        return self._copy(
            order=(*self.order, *((self._formula(k), direction) for k in keys))
        )

    def offset(self, n: int) -> Table:
        """Skip the first ``n`` records."""
        if n < 0:
            raise ValueError("offset must be >= 0")
        return self._copy(skip=n)

    def limit(self, n: int | None) -> Table:
        """Return at most ``n`` records (``None``: no limit)."""
        if n is not None and n < 0:
            raise ValueError("limit must be >= 0")
        return self._copy(max_rows=n)

    def _formula(self, key: str) -> str:
        """A field (by code, id or label) as a formula; anything else as-is."""
        try:
            return self._schema().field(key).id
        except LookupError:
            return key

    @property
    def filter_formula(self) -> str | None:
        return " && ".join(self.filters) if self.filters else None

    def columns(self) -> dict[str, str]:
        """``{column name: formula}`` of the query."""
        return {name: formula for name, (formula, _) in self._columns().items()}

    def _columns(self) -> dict[str, tuple[str, FormField | None]]:
        if self.selected is None:
            return default_columns(self._schema(), self._related(), names=self.names)
        return {
            name: (formula, self._field_for(formula)) for name, formula in self.selected
        }

    def _field_for(self, formula: str) -> FormField | None:
        """The field a formula reads, when it is a plain or dotted field id."""
        head, _, rest = formula.partition(".")
        try:
            form_field = self._schema().field(head)
        except LookupError:
            return None
        if not rest:
            return form_field
        if isinstance(form_field, ReferenceField):
            referenced = self._related().get(form_field.form_id)
            if referenced and "." not in rest:
                try:
                    return referenced.field(rest)
                except LookupError:
                    return None
        return None

    # -- Running the query -------------------------------------------------

    def collect(self) -> list[dict[str, Any]]:
        """Run the query and return one dict per record.

        Values are converted like ``form.records``: dates become
        :class:`datetime.date`, select options their labels, references the
        referenced record id.
        """
        columns = self._columns()
        result = self.form.database.client.queries.columns(
            self.form.id,
            {name: formula for name, (formula, _) in columns.items()},
            filter=self.filter_formula,
            sort=list(self.order) or None,
            offset=self.skip,
            limit=self.max_rows,
        )
        fields = {name: f for name, (_, f) in columns.items() if f is not None}
        return [
            {
                name: decode_value(fields[name], value) if name in fields else value
                for name, value in row.items()
            }
            for row in result
        ]

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self.collect())

    def first(self) -> dict[str, Any] | None:
        """The first record, or ``None``."""
        rows = self.limit(1).collect()
        return rows[0] if rows else None

    def count(self) -> int:
        """The number of records matching the filters (ignores offset/limit)."""
        result = self.form.database.client.queries.columns(
            self.form.id, {ID_COLUMN: "_id"}, filter=self.filter_formula
        )
        return len(result)

    def to_pandas(self) -> Any:
        """Run the query and return a :class:`pandas.DataFrame`.

        Date fields become ``datetime64`` columns.
        """
        from .._pandas import require_pandas
        from .fields import DateField

        pd = require_pandas()
        columns = self._columns()
        frame = pd.DataFrame(self.collect(), columns=list(columns))
        for name, (_, form_field) in columns.items():
            if isinstance(form_field, DateField):
                frame[name] = pd.to_datetime(frame[name], errors="coerce")
        return frame
