import pytest

from activipyinfo import (
    DateField,
    FormSchema,
    MultipleMatchesError,
    NoMatchError,
    QuantityField,
    SubformField,
    TextField,
)


@pytest.fixture
def schema():
    return FormSchema(
        "Households",
        [
            TextField("Head", code="head", key=True, id="fhead"),
            QuantityField("Members", code="members", id="fmembers"),
            DateField("Visit date", id="fdate"),
        ],
        id="chh",
    )


def test_round_trip_of_every_field_type(all_types_schema_data):
    data = all_types_schema_data

    schema = FormSchema.from_api(data)

    assert len(schema) == 21
    assert schema.schema_version == 7
    assert schema.extra == {"translationConfig": {"languages": ["fr"]}}
    assert schema.to_api() == data


def test_serialization(schema):
    schema.database_id = "db1"

    data = schema.to_api()

    assert data["id"] == "chh"
    assert data["label"] == "Households"
    assert data["databaseId"] == "db1"
    assert "schemaVersion" not in data
    assert "parentFormId" not in data
    assert [e["id"] for e in data["elements"]] == ["fhead", "fmembers", "fdate"]


def test_subform_serialization():
    data = FormSchema("Members", parent_form_id="chh", id="cm").to_api()

    assert data["parentFormId"] == "chh"


def test_field_lookup(schema):
    assert schema.field("fhead").code == "head"
    assert schema.field("members").id == "fmembers"
    assert schema["Visit date"].id == "fdate"
    assert "head" in schema
    assert schema.fields[0] in schema
    assert "nothing" not in schema

    with pytest.raises(NoMatchError):
        schema.field("nothing")


def test_ambiguous_label(schema):
    schema.add_field(DateField("Visit date", id="fdate2"))

    with pytest.raises(MultipleMatchesError):
        schema.field("Visit date")


def test_iteration_and_key_fields(schema):
    assert [f.id for f in schema] == ["fhead", "fmembers", "fdate"]
    assert schema.key_fields == [schema["head"]]


def test_add_field_at_end_and_after(schema):
    schema.add_field(TextField("Phone", code="phone", id="fphone"))
    schema.add_field(TextField("Village", id="fvillage"), after="head")

    assert [f.id for f in schema] == [
        "fhead",
        "fvillage",
        "fmembers",
        "fdate",
        "fphone",
    ]


def test_add_field_rejects_duplicate_code(schema):
    with pytest.raises(ValueError, match="Duplicate field codes"):
        schema.add_field(TextField("Other head", code="head"))

    assert len(schema) == 3


def test_constructor_rejects_duplicate_ids():
    with pytest.raises(ValueError, match="Duplicate field ids"):
        FormSchema("F", [DateField("A", id="fa"), DateField("B", id="fa")])


def test_invalid_form_id():
    with pytest.raises(ValueError, match="form id"):
        FormSchema("F", id="1abc")


def test_remove_field(schema):
    removed = schema.remove_field("members")

    assert removed.id == "fmembers"
    assert [f.id for f in schema] == ["fhead", "fdate"]


def test_subform_fields():
    schema = FormSchema("F", [SubformField("Members", "cm"), DateField("D")])

    assert [f.subform_id for f in schema.subform_fields] == ["cm"]


def test_describe(schema):
    rows = schema.describe()

    assert rows[0] == {
        "field_id": "fhead",
        "code": "head",
        "label": "Head",
        "type": "FREE_TEXT",
        "key": True,
        "required": True,
        "description": None,
        "relevance": None,
        "validation": None,
    }


def test_str(schema):
    assert str(schema).splitlines() == [
        "Form 'Households' (chh)",
        "  head                 FREE_TEXT              Head  [key]",
        "  members              quantity               Members",
        "  -                    date                   Visit date",
    ]
