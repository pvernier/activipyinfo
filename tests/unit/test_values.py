from datetime import date, datetime

import pytest

from activipyinfo import (
    AttachmentField,
    CalculatedField,
    DateField,
    GeoPointField,
    MonthField,
    MultilineField,
    MultiReferenceField,
    MultiSelectField,
    QuantityField,
    Record,
    ReferenceField,
    SelectOption,
    SerialNumberField,
    SingleSelectField,
    SubformField,
    TextField,
    WeekField,
)
from activipyinfo.models.values import decode_value, encode_value

SEX = SingleSelectField(
    "Sex", [SelectOption("Female", id="f"), SelectOption("Male", id="m")]
)
NEEDS = MultiSelectField(
    "Needs", [SelectOption("Food", id="food"), SelectOption("Water", id="water")]
)


# ----------------------------------------------------------------------
# encode_value
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        (TextField("T"), "Alice", "Alice"),
        (MultilineField("M"), "a\nb", "a\nb"),
        (QuantityField("Q"), 42, 42),
        (QuantityField("Q"), 2.5, 2.5),
        (DateField("D"), date(2024, 3, 1), "2024-03-01"),
        (DateField("D"), datetime(2024, 3, 1, 15, 30), "2024-03-01"),
        (DateField("D"), "2024-03-01", "2024-03-01"),
        (MonthField("M"), date(2024, 3, 17), "2024-03"),
        (MonthField("M"), "2024-03", "2024-03"),
        (WeekField("W"), "2024W7", "2024W7"),
        (SEX, "Female", "f"),
        (SEX, "m", "m"),
        (SEX, SelectOption("Male", id="m"), "m"),
        (NEEDS, ["Food", "water"], ["food", "water"]),
        (NEEDS, "Water", ["water"]),
        (ReferenceField("R", "cform"), "rec1", "rec1"),
        (ReferenceField("R", "cform"), Record("rec1", "cform"), "rec1"),
        (
            MultiReferenceField("R", "cform"),
            ["r1", Record("r2", "cform")],
            ["r1", "r2"],
        ),
        (GeoPointField("G"), (52.07, 4.33), {"latitude": 52.07, "longitude": 4.33}),
        (
            GeoPointField("G"),
            (52.07, 4.33, 12),
            {"latitude": 52.07, "longitude": 4.33, "accuracy": 12},
        ),
        (
            GeoPointField("G"),
            {"latitude": 1.0, "longitude": 2.0},
            {"latitude": 1.0, "longitude": 2.0},
        ),
        (AttachmentField("A"), [{"blobId": "b1"}], [{"blobId": "b1"}]),
        (TextField("T"), None, None),
    ],
)
def test_encode(field, value, expected):
    assert encode_value(field, value) == expected


@pytest.mark.parametrize(
    ("field", "value", "error", "match"),
    [
        (QuantityField("Q"), "42", TypeError, "number"),
        (QuantityField("Q"), True, TypeError, "number"),
        (DateField("D"), "01/03/2024", ValueError, "YYYY-MM-DD"),
        (DateField("D"), 20240301, TypeError, "string"),
        (WeekField("W"), date(2024, 1, 1), TypeError, "epidemiological"),
        (SEX, "Other", ValueError, "not an option"),
        (NEEDS, ["Food", "Fuel"], ValueError, "not an option"),
        (GeoPointField("G"), (1.0,), TypeError, "latitude"),
        (GeoPointField("G"), {"lat": 1.0}, ValueError, "latitude"),
        (ReferenceField("R", "c"), 42, TypeError, "record id"),
        (TextField("T"), 42, None, None),
    ],
)
def test_encode_rejects_invalid_values(field, value, error, match):
    if error is None:  # text fields do not check types: the server does
        assert encode_value(field, value) == value
        return
    with pytest.raises(error, match=match):
        encode_value(field, value)


@pytest.mark.parametrize(
    "field",
    [
        CalculatedField("C", "1"),
        SerialNumberField("S"),
        SubformField("Sub", "csub"),
    ],
)
def test_read_only_fields_cannot_be_written(field):
    with pytest.raises(ValueError, match="read-only"):
        encode_value(field, "x")


# ----------------------------------------------------------------------
# decode_value
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        (DateField("D"), "2024-03-01", date(2024, 3, 1)),
        (DateField("D"), "not a date", "not a date"),
        (SEX, "f", "Female"),
        (SEX, "Male", "Male"),
        (SEX, "unknown", "unknown"),
        (NEEDS, ["food", "water"], ["Food", "Water"]),
        (ReferenceField("R", "cform"), "cform:rec1", "rec1"),
        (ReferenceField("R", "cform"), "rec1", "rec1"),
        (MultiReferenceField("R", "cform"), ["cform:r1", "r2"], ["r1", "r2"]),
        (QuantityField("Q"), 3, 3),
        (MonthField("M"), "2024-03", "2024-03"),
        (TextField("T"), None, None),
    ],
)
def test_decode(field, value, expected):
    assert decode_value(field, value) == expected
