import string

import pytest

from activipyinfo.field import Field
from activipyinfo.ids import cuid, is_cuid
from activipyinfo.record import Record

ALPHANUMERIC = string.ascii_lowercase + string.digits


def test_cuid_shape():
    unique_id = cuid()

    assert len(unique_id) == 24
    assert unique_id[0] in string.ascii_lowercase
    assert all(c in ALPHANUMERIC for c in unique_id[1:])


def test_cuid_custom_length():
    assert len(cuid(10)) == 10


@pytest.mark.parametrize("length", [1, 33])
def test_cuid_rejects_invalid_length(length):
    with pytest.raises(ValueError):
        cuid(length)


def test_cuids_are_unique():
    ids = {cuid() for _ in range(10_000)}

    assert len(ids) == 10_000


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("ck8oykh8m5", True),
        (cuid(), True),
        ("1abc", False),
        ("Abc", False),
        ("ab-c", False),
        ("a", False),
        (None, False),
    ],
)
def test_is_cuid(value, expected):
    assert is_cuid(value) is expected


def test_field_uses_provided_id():
    field = Field({"code": "name"}, id="abc123")

    assert field.id == "abc123"
    assert field.data == {"code": "name"}


def test_field_generates_cuid_by_default():
    assert is_cuid(Field({"code": "name"}).id)


def test_record_sets_fields_and_values():
    field = Field({"code": "name"}, id="field_id")
    record = Record([field], ["Alice"])

    assert is_cuid(record.id)
    assert record.fields == [field]
    assert record.values == ["Alice"]
