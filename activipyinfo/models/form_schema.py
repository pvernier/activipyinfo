from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import KW_ONLY, dataclass, field
from typing import Any

from ..ids import cuid
from ._common import one
from .fields import FormField, SubformField

__all__ = ["FormSchema"]

_FORM_ID = re.compile(r"^[A-Za-z][A-Za-z0-9]{0,31}$")
_HANDLED_KEYS = {
    "id",
    "label",
    "databaseId",
    "parentFormId",
    "schemaVersion",
    "elements",
}


@dataclass(eq=False)
class FormSchema:
    """The structure of a form: its label and its fields.

    Fields can be looked up by id, code or label: ``schema["name"]``.

    Example:
        >>> schema = FormSchema("Households", [
        ...     TextField("Head of household", code="head", key=True),
        ...     QuantityField("Members", code="members"),
        ... ])
        >>> db.add_form(schema)
    """

    label: str
    fields: list[FormField] = field(default_factory=list)
    _: KW_ONLY
    id: str = field(default_factory=cuid)
    database_id: str | None = None
    parent_form_id: str | None = None
    schema_version: Any = None
    extra: dict[str, Any] = field(default_factory=dict, repr=False)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if not _FORM_ID.match(self.id):
            raise ValueError(
                f"Invalid form id {self.id!r}: it must start with a letter and "
                "contain up to 32 letters or digits."
            )
        self.fields = list(self.fields)
        self.validate()

    def __repr__(self) -> str:
        return f"FormSchema({self.label!r}, id={self.id!r}, fields={len(self.fields)})"

    def __str__(self) -> str:
        lines = [f"Form {self.label!r} ({self.id})"]
        if self.parent_form_id:
            lines.append(f"  subform of {self.parent_form_id}")
        for f in self.fields:
            flags = [
                flag
                for flag, on in (("key", f.key), ("required", f.required and not f.key))
                if on
            ]
            code = f.code or "-"
            suffix = f"  [{', '.join(flags)}]" if flags else ""
            lines.append(f"  {code:<20} {f.type:<22} {f.label}{suffix}")
        return "\n".join(lines)

    # -- Container behaviour ----------------------------------------------

    def __iter__(self) -> Iterator[FormField]:
        return iter(self.fields)

    def __len__(self) -> int:
        return len(self.fields)

    def __getitem__(self, key: str) -> FormField:
        return self.field(key)

    def __contains__(self, key: object) -> bool:
        if isinstance(key, FormField):
            return any(f.id == key.id for f in self.fields)
        return any(key in (f.id, f.code, f.label) for f in self.fields)

    def field(self, key: str) -> FormField:
        """Return a field by id, code or (unique) label."""
        for f in self.fields:
            if key in (f.id, f.code):
                return f
        return one(
            (f for f in self.fields if f.label == key),
            f"field {key!r} in {self!r}",
        )

    @property
    def key_fields(self) -> list[FormField]:
        return [f for f in self.fields if f.key]

    @property
    def subform_fields(self) -> list[SubformField]:
        return [f for f in self.fields if isinstance(f, SubformField)]

    # -- Editing ---------------------------------------------------------

    def add_field(
        self, new_field: FormField, *, after: FormField | str | None = None
    ) -> FormField:
        """Add a field at the end, or right after another field."""
        position = len(self.fields)
        if after is not None:
            anchor = after if isinstance(after, FormField) else self.field(after)
            position = self.fields.index(anchor) + 1
        self.fields.insert(position, new_field)
        try:
            self.validate()
        except ValueError:
            self.fields.remove(new_field)
            raise
        return new_field

    def remove_field(self, key: FormField | str) -> FormField:
        """Remove a field (by object, id, code or label) and return it."""
        removed = key if isinstance(key, FormField) else self.field(key)
        self.fields = [f for f in self.fields if f.id != removed.id]
        return removed

    def validate(self) -> None:
        """Check that field ids and codes are unique."""
        for attribute in ("id", "code"):
            values = [getattr(f, attribute) for f in self.fields]
            values = [v for v in values if v]
            duplicates = sorted({v for v in values if values.count(v) > 1})
            if duplicates:
                raise ValueError(f"Duplicate field {attribute}s: {duplicates}")

    # -- Serialization ---------------------------------------------------

    def describe(self) -> list[dict[str, Any]]:
        """One row per field, like the R package's ``as.data.frame(schema)``."""
        return [
            {
                "field_id": f.id,
                "code": f.code,
                "label": f.label,
                "type": f.type,
                "key": f.key,
                "required": f.required,
                "description": f.description,
                "relevance": f.relevance,
                "validation": f.validation,
            }
            for f in self.fields
        ]

    def to_api(self) -> dict[str, Any]:
        data: dict[str, Any] = {"id": self.id, "label": self.label}
        if self.database_id:
            data["databaseId"] = self.database_id
        if self.parent_form_id:
            data["parentFormId"] = self.parent_form_id
        if self.schema_version is not None:
            data["schemaVersion"] = self.schema_version
        data["elements"] = [f.to_api() for f in self.fields]
        return {**data, **self.extra}

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> FormSchema:
        schema = cls.__new__(cls)
        # Skip validation: the server's schema is authoritative.
        schema.label = data.get("label", "")
        schema.fields = [FormField.from_api(e) for e in data.get("elements") or []]
        schema.id = data["id"]
        schema.database_id = data.get("databaseId")
        schema.parent_form_id = data.get("parentFormId")
        schema.schema_version = data.get("schemaVersion")
        schema.extra = {k: v for k, v in data.items() if k not in _HANDLED_KEYS}
        schema.raw = data
        return schema
