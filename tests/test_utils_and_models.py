import string

from activipyinfo.field import Field
from activipyinfo.record import Record
from activipyinfo.utils import create_unique_id


def test_create_unique_id_shape():
    unique_id = create_unique_id()

    assert len(unique_id) == 24
    assert unique_id[0] in string.ascii_lowercase
    assert all(c in (string.ascii_lowercase + string.digits) for c in unique_id[1:])


def test_field_uses_provided_id():
    field = Field({"code": "name"}, id="abc123")

    assert field.id == "abc123"
    assert field.data == {"code": "name"}


def test_record_sets_fields_and_values():
    field = Field({"code": "name"}, id="field_id")
    record = Record([field], ["Alice"])

    assert len(record.id) == 24
    assert record.fields == [field]
    assert record.values == ["Alice"]
