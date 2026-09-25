"""Form field types.

One class per ActivityInfo field type, modelled on the R package's
``*FieldSchema()`` builders. Every class round-trips the API JSON: element
properties and ``typeParameters`` that a class does not model are kept in
``extra`` and ``extra_parameters`` and sent back unchanged.

Example:
    >>> TextField("Name", code="name", key=True)
    >>> SingleSelectField("Sex", options=["Female", "Male"])
    >>> ReferenceField("Province", form=provinces_form)
"""

from __future__ import annotations

import re
from dataclasses import KW_ONLY, dataclass, field
from enum import StrEnum
from typing import Any, ClassVar

from ..ids import cuid

__all__ = [
    "AttachmentField",
    "CalculatedField",
    "DateField",
    "FieldType",
    "FormField",
    "FortnightField",
    "GeoPointField",
    "MonthField",
    "MultiReferenceField",
    "MultiSelectField",
    "MultilineField",
    "NoteField",
    "QuantityField",
    "ReferenceField",
    "ReverseReferenceField",
    "SectionHeader",
    "SelectOption",
    "SerialNumberField",
    "SingleSelectField",
    "SubformField",
    "TextField",
    "UnknownField",
    "UserField",
    "WeekField",
]

_FIELD_ID = re.compile(r"^[A-Za-z][A-Za-z0-9]{0,31}$")
_FIELD_CODE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")


class FieldType(StrEnum):
    """Field types, as named by the API (note the mixed case)."""

    TEXT = "FREE_TEXT"
    MULTILINE = "NARRATIVE"
    QUANTITY = "quantity"
    DATE = "date"
    WEEK = "epiweek"
    FORTNIGHT = "fortnight"
    MONTH = "month"
    SELECT = "enumerated"
    REFERENCE = "reference"
    MULTI_REFERENCE = "multiselectreference"
    REVERSE_REFERENCE = "reversereference"
    SUBFORM = "subform"
    CALCULATED = "calculated"
    SERIAL = "serial"
    GEOPOINT = "geopoint"
    ATTACHMENT = "attachment"
    SECTION = "section"
    NOTE = "note"


def _id_of(value: Any) -> str:
    return value if isinstance(value, str) else value.id


# Element properties modelled by FormField: attribute name -> API key.
_COMMON_PROPERTIES = {
    "code": "code",
    "description": "description",
    "required": "required",
    "key": "key",
    "relevance": "relevanceCondition",
    "validation": "validationCondition",
    "validation_message": "validationMessage",
    "required_condition": "requiredCondition",
}
_HANDLED_KEYS = {
    "id",
    "label",
    "type",
    "typeParameters",
    "dataEntryVisible",
    "tableVisible",
    *_COMMON_PROPERTIES.values(),
}


@dataclass(eq=False)
class FormField:
    """Base class of all field types.

    Args:
        label: Label shown to users.
        code: Short name usable in formulas and in the API (letters, digits
            and underscores, starting with a letter, max 32).
        description: Help text shown during data entry.
        required: Whether a value is required. Key fields are always required.
        key: Whether the field is part of the form's key (unique per record).
        relevance: Formula; the field is only shown when it is true.
        validation: Formula that valid values must satisfy.
        validation_message: Message shown when ``validation`` fails.
        required_condition: Formula; the field is only required when true.
        hidden: Hide the field during data entry.
        hidden_in_table: Hide the column in the table view by default.
        id: Field id, generated if omitted.
    """

    TYPE: ClassVar[str] = ""
    CAN_BE_KEY: ClassVar[bool] = False
    # Simple typeParameters: attribute name -> API key.
    PARAMETERS: ClassVar[dict[str, str]] = {}

    label: str
    _: KW_ONLY
    code: str | None = None
    description: str | None = None
    required: bool = False
    key: bool = False
    relevance: str | None = None
    validation: str | None = None
    validation_message: str | None = None
    required_condition: str | None = None
    hidden: bool = False
    hidden_in_table: bool = False
    id: str = field(default_factory=cuid)
    extra: dict[str, Any] = field(default_factory=dict, repr=False)
    extra_parameters: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if not _FIELD_ID.match(self.id):
            raise ValueError(
                f"Invalid field id {self.id!r}: it must start with a letter and "
                "contain up to 32 letters or digits."
            )
        if self.code is not None and not _FIELD_CODE.match(self.code):
            raise ValueError(
                f"Invalid field code {self.code!r}: it must start with a letter "
                "and contain up to 32 letters, digits or underscores."
            )
        if self.key:
            if not self.CAN_BE_KEY:
                raise ValueError(f"{type(self).__name__} cannot be a key field")
            self.required = True

    @property
    def type(self) -> str:
        return self.TYPE

    def __repr__(self) -> str:
        code = f", code={self.code!r}" if self.code else ""
        return f"{type(self).__name__}({self.label!r}{code})"

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, FormField)
            and type(other) is type(self)
            and other.to_api() == self.to_api()
        )

    __hash__ = None  # type: ignore[assignment]

    # -- Serialization ---------------------------------------------------

    def type_parameters(self) -> dict[str, Any]:
        """The ``typeParameters`` object of this field."""
        params = {
            api_key: getattr(self, attr)
            for attr, api_key in self.PARAMETERS.items()
            if getattr(self, attr) is not None
        }
        params.update(self._complex_parameters())
        return {**params, **self.extra_parameters}

    def _complex_parameters(self) -> dict[str, Any]:
        return {}

    def to_api(self) -> dict[str, Any]:
        """Serialize as a form schema element."""
        data: dict[str, Any] = {"id": self.id}
        if self.code:
            data["code"] = self.code
        data["label"] = self.label
        if self.description:
            data["description"] = self.description
        data["type"] = str(self.type)
        data["required"] = self.required
        data["key"] = self.key
        data["relevanceCondition"] = self.relevance or ""
        data["validationCondition"] = self.validation or ""
        if self.validation_message:
            data["validationMessage"] = self.validation_message
        if self.required_condition:
            data["requiredCondition"] = self.required_condition
        data["dataEntryVisible"] = not self.hidden
        data["tableVisible"] = not self.hidden_in_table
        params = self.type_parameters()
        if params:
            data["typeParameters"] = params
        return {**data, **self.extra}

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> FormField:
        """Parse a form schema element into the matching field class."""
        klass = _field_class(data)
        params = dict(data.get("typeParameters") or {})
        kwargs: dict[str, Any] = {
            "id": data["id"],
            "label": data.get("label", ""),
            "hidden": data.get("dataEntryVisible") is False,
            "hidden_in_table": data.get("tableVisible") is False,
            "extra": {k: v for k, v in data.items() if k not in _HANDLED_KEYS},
        }
        for attr, api_key in _COMMON_PROPERTIES.items():
            if data.get(api_key) not in (None, ""):
                kwargs[attr] = data[api_key]
        for attr, api_key in klass.PARAMETERS.items():
            if api_key in params:
                kwargs[attr] = params.pop(api_key)
        kwargs.update(klass._parse_parameters(params, data))
        kwargs["extra_parameters"] = params
        field_ = klass.__new__(klass)
        # Bypass key validation: the server's schema is authoritative.
        klass.__init__(field_, **{**kwargs, "key": False})
        field_.key = bool(data.get("key", False))
        field_.required = bool(data.get("required", False))
        return field_

    @classmethod
    def _parse_parameters(
        cls, params: dict[str, Any], data: dict[str, Any]
    ) -> dict[str, Any]:
        """Extract complex typeParameters (popping them from ``params``)."""
        return {}


# ----------------------------------------------------------------------
# Text, numbers and dates
# ----------------------------------------------------------------------


@dataclass(eq=False, repr=False)
class TextField(FormField):
    """Single-line text (``FREE_TEXT``). Can be a key field."""

    TYPE = FieldType.TEXT
    CAN_BE_KEY = True
    PARAMETERS = {"input_mask": "inputMask", "barcode": "barcode"}

    _: KW_ONLY
    input_mask: str | None = None
    barcode: bool = False


@dataclass(eq=False, repr=False)
class MultilineField(FormField):
    """Multi-line text (``NARRATIVE``)."""

    TYPE = FieldType.MULTILINE


@dataclass(eq=False, repr=False)
class QuantityField(FormField):
    """A number, with optional units."""

    TYPE = FieldType.QUANTITY
    PARAMETERS = {"units": "units", "aggregation": "aggregation"}

    _: KW_ONLY
    units: str = ""
    aggregation: str | None = "SUM"


@dataclass(eq=False, repr=False)
class DateField(FormField):
    """A date (``YYYY-MM-DD``)."""

    TYPE = FieldType.DATE
    CAN_BE_KEY = True


@dataclass(eq=False, repr=False)
class WeekField(FormField):
    """An epidemiological week (``YYYY-Www``)."""

    TYPE = FieldType.WEEK
    CAN_BE_KEY = True


@dataclass(eq=False, repr=False)
class FortnightField(FormField):
    """A two-week period (deprecated by ActivityInfo)."""

    TYPE = FieldType.FORTNIGHT
    CAN_BE_KEY = True


@dataclass(eq=False, repr=False)
class MonthField(FormField):
    """A month (``YYYY-MM``)."""

    TYPE = FieldType.MONTH
    CAN_BE_KEY = True


@dataclass(eq=False, repr=False)
class SerialNumberField(FormField):
    """An automatically incremented number, always a required key field."""

    TYPE = FieldType.SERIAL
    CAN_BE_KEY = True
    PARAMETERS = {"digits": "digits", "prefix_formula": "prefixFormula"}

    _: KW_ONLY
    key: bool = True
    required: bool = True
    digits: int | None = 5
    prefix_formula: str | None = None


@dataclass(eq=False, repr=False)
class CalculatedField(FormField):
    """A read-only value computed from a formula."""

    TYPE = FieldType.CALCULATED
    PARAMETERS = {"formula": "formula"}

    formula: str = ""


# ----------------------------------------------------------------------
# Selections
# ----------------------------------------------------------------------


@dataclass
class SelectOption:
    """An option of a single or multiple selection field."""

    label: str
    id: str = field(default_factory=cuid)

    @classmethod
    def coerce(cls, value: SelectOption | str | dict[str, Any]) -> SelectOption:
        if isinstance(value, SelectOption):
            return value
        if isinstance(value, str):
            return cls(value)
        return cls(label=value["label"], id=value["id"])

    def to_api(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label}


@dataclass(eq=False, repr=False)
class _SelectField(FormField):
    TYPE = FieldType.SELECT
    CAN_BE_KEY = True
    CARDINALITY: ClassVar[str] = ""
    PARAMETERS = {"presentation": "presentation"}

    options: list[SelectOption] = field(default_factory=list)
    _: KW_ONLY
    presentation: str | None = "automatic"

    def __post_init__(self) -> None:
        self.options = [SelectOption.coerce(o) for o in self.options]
        labels = [o.label for o in self.options]
        if len(set(labels)) != len(labels):
            raise ValueError(f"Duplicate options in {self.label!r}")
        super().__post_init__()

    def option(self, label_or_id: str) -> SelectOption:
        """Return an option by label or id."""
        for option in self.options:
            if label_or_id in (option.id, option.label):
                return option
        raise KeyError(f"{self.label!r} has no option {label_or_id!r}")

    def _complex_parameters(self) -> dict[str, Any]:
        return {
            "cardinality": self.CARDINALITY,
            "values": [o.to_api() for o in self.options],
        }

    @classmethod
    def _parse_parameters(
        cls, params: dict[str, Any], data: dict[str, Any]
    ) -> dict[str, Any]:
        params.pop("cardinality", None)
        return {"options": [SelectOption.coerce(v) for v in params.pop("values", [])]}


@dataclass(eq=False, repr=False)
class SingleSelectField(_SelectField):
    """Choose one option from a list."""

    CARDINALITY = "single"


@dataclass(eq=False, repr=False)
class MultiSelectField(_SelectField):
    """Choose any number of options from a list."""

    CARDINALITY = "multiple"


# ----------------------------------------------------------------------
# References and subforms
# ----------------------------------------------------------------------


@dataclass(eq=False, repr=False)
class ReferenceField(FormField):
    """A link to one record of another form (``form`` accepts a Form or an id)."""

    TYPE = FieldType.REFERENCE
    CAN_BE_KEY = True
    PARAMETERS = {"lookup_configs": "lookupConfigs"}

    form: Any = ""
    _: KW_ONLY
    lookup_configs: list[dict[str, Any]] | None = None

    def __post_init__(self) -> None:
        self.form = _id_of(self.form)
        super().__post_init__()

    @property
    def form_id(self) -> str:
        return str(self.form)

    def _complex_parameters(self) -> dict[str, Any]:
        return {"cardinality": "single", "range": [{"formId": self.form_id}]}

    @classmethod
    def _parse_parameters(
        cls, params: dict[str, Any], data: dict[str, Any]
    ) -> dict[str, Any]:
        params.pop("cardinality", None)
        range_ = params.pop("range", None) or [{}]
        if len(range_) > 1:
            params["range"] = range_  # several forms: keep them all as-is
        return {"form": range_[0].get("formId", "")}


@dataclass(eq=False, repr=False)
class UserField(ReferenceField):
    """Select a user of the database (a reference to ``<database>@users``)."""

    def __init__(self, label: str, database: Any = "", **kwargs: Any) -> None:
        database_id = _id_of(database)
        form = kwargs.pop("form", f"{database_id}@users")
        super().__init__(label, form, **kwargs)

    @property
    def database_id(self) -> str:
        return self.form_id.removesuffix("@users")


@dataclass(eq=False, repr=False)
class MultiReferenceField(FormField):
    """Links to any number of records of another form."""

    TYPE = FieldType.MULTI_REFERENCE
    PARAMETERS = {"lookup_configs": "lookupConfigs"}

    form: Any = ""
    _: KW_ONLY
    lookup_configs: list[dict[str, Any]] | None = None

    def __post_init__(self) -> None:
        self.form = _id_of(self.form)
        super().__post_init__()

    @property
    def form_id(self) -> str:
        return str(self.form)

    def _complex_parameters(self) -> dict[str, Any]:
        return {"range": [{"formId": self.form_id}]}

    @classmethod
    def _parse_parameters(
        cls, params: dict[str, Any], data: dict[str, Any]
    ) -> dict[str, Any]:
        range_ = params.pop("range", None) or [{}]
        if len(range_) > 1:
            params["range"] = range_
        return {"form": range_[0].get("formId", "")}


@dataclass(eq=False, repr=False)
class ReverseReferenceField(FormField):
    """Lists the records of another form that reference this record."""

    TYPE = FieldType.REVERSE_REFERENCE
    PARAMETERS = {"form_id": "formId", "field_id": "fieldId"}

    _: KW_ONLY
    form_id: str | None = None
    field_id: str | None = None


@dataclass(eq=False, repr=False)
class SubformField(FormField):
    """Repeating records stored in a subform (``subform`` accepts a Form or an id)."""

    TYPE = FieldType.SUBFORM

    subform: Any = ""

    def __post_init__(self) -> None:
        self.subform = _id_of(self.subform)
        super().__post_init__()

    @property
    def subform_id(self) -> str:
        return str(self.subform)

    def _complex_parameters(self) -> dict[str, Any]:
        return {"formId": self.subform_id}

    @classmethod
    def _parse_parameters(
        cls, params: dict[str, Any], data: dict[str, Any]
    ) -> dict[str, Any]:
        return {"subform": params.pop("formId", "")}


# ----------------------------------------------------------------------
# Location, files and layout
# ----------------------------------------------------------------------


@dataclass(eq=False, repr=False)
class GeoPointField(FormField):
    """A GPS point. ``required_accuracy`` is in metres."""

    TYPE = FieldType.GEOPOINT
    PARAMETERS = {
        "required_accuracy": "requiredAccuracy",
        "manual_entry_allowed": "manualEntryAllowed",
    }

    _: KW_ONLY
    required_accuracy: float | None = None
    manual_entry_allowed: bool | None = True


@dataclass(eq=False, repr=False)
class AttachmentField(FormField):
    """Files, photos or signatures attached to a record."""

    TYPE = FieldType.ATTACHMENT
    PARAMETERS = {
        "cardinality": "cardinality",
        "capture_methods": "captureMethods",
        "file_types": "fileTypes",
    }

    _: KW_ONLY
    cardinality: str | None = "multiple"
    capture_methods: list[str] | None = field(
        default_factory=lambda: ["CAMERA", "FILE", "SIGNATURE"]
    )
    file_types: list[str] | None = None


@dataclass(eq=False, repr=False)
class SectionHeader(FormField):
    """A section title that groups the following fields."""

    TYPE = FieldType.SECTION
    PARAMETERS = {"indentation_level": "indentationLevel"}

    _: KW_ONLY
    indentation_level: int | None = 1


@dataclass(eq=False, repr=False)
class NoteField(FormField):
    """Display-only text (label and description), with no value."""

    TYPE = FieldType.NOTE


@dataclass(eq=False, repr=False)
class UnknownField(FormField):
    """A field type this library does not know yet; kept as-is."""

    _: KW_ONLY
    raw_type: str = ""

    @property
    def type(self) -> str:
        return self.raw_type

    @classmethod
    def _parse_parameters(
        cls, params: dict[str, Any], data: dict[str, Any]
    ) -> dict[str, Any]:
        return {"raw_type": data.get("type", "")}


_TYPE_CLASSES: dict[str, type[FormField]] = {
    str(klass.TYPE).lower(): klass
    for klass in (
        TextField,
        MultilineField,
        QuantityField,
        DateField,
        WeekField,
        FortnightField,
        MonthField,
        ReferenceField,
        MultiReferenceField,
        ReverseReferenceField,
        SubformField,
        CalculatedField,
        SerialNumberField,
        GeoPointField,
        AttachmentField,
        SectionHeader,
        NoteField,
    )
}


def _field_class(data: dict[str, Any]) -> type[FormField]:
    field_type = str(data.get("type", "")).lower()
    params = data.get("typeParameters") or {}
    if field_type == FieldType.SELECT:
        if str(params.get("cardinality", "single")).lower() == "multiple":
            return MultiSelectField
        return SingleSelectField
    if field_type == FieldType.REFERENCE:
        range_ = params.get("range") or []
        if len(range_) == 1 and str(range_[0].get("formId", "")).endswith("@users"):
            return UserField
    return _TYPE_CLASSES.get(field_type, UnknownField)
