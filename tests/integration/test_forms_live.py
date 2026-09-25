"""Live checks of forms and schemas. They run in a scratch folder (see conftest.py)."""

import pytest

from activipyinfo import (
    CalculatedField,
    DateField,
    FormSchema,
    MultiSelectField,
    NoMatchError,
    QuantityField,
    ReferenceField,
    SingleSelectField,
    SubForm,
    SubformField,
    TextField,
)

pytestmark = pytest.mark.integration


def test_form_lifecycle(sandbox):
    folder = sandbox.folder

    provinces = folder.add_form(
        "Provinces",
        [
            TextField("P-code", code="pcode", key=True),
            TextField("Name", code="name", required=True),
        ],
    )
    households = folder.add_form(
        FormSchema(
            "Households",
            [
                ReferenceField("Province", provinces, code="province", required=True),
                TextField("Head of household", code="head", key=True),
                QuantityField("Members", code="members", units="people"),
                SingleSelectField("Status", ["Resident", "Displaced"], code="status"),
                MultiSelectField("Needs", ["Food", "Water", "Shelter"], code="needs"),
                DateField("Visit date", code="visit"),
                CalculatedField("Large", "members > 5", code="large"),
            ],
        )
    )
    assert provinces.parent.id == folder.id

    # What the server kept of what we sent (lower-case select cardinality...).
    schema = households.schema()
    assert schema["province"].form_id == provinces.id
    assert schema["head"].key is True
    assert schema["members"].units == "people"
    assert type(schema["needs"]) is MultiSelectField
    assert [o.label for o in schema["status"].options] == ["Resident", "Displaced"]
    assert schema["large"].formula == "members > 5"

    households.add_field(TextField("Phone", code="phone"), after="head")
    assert [f.code for f in households.schema()][:3] == ["province", "head", "phone"]

    households.delete_field("phone")
    with pytest.raises(NoMatchError):
        households.schema().field("phone")

    # Open question: does the server link a new subform from its parent?
    members = households.add_subform("Members", [TextField("Name", code="name")])
    assert isinstance(members, SubForm)
    links = [
        f
        for f in households.schema()
        if isinstance(f, SubformField) and f.subform_id == members.id
    ]
    assert len(links) == 1

    copy = provinces.duplicate()
    try:
        assert copy.id != provinces.id
        assert [f.code for f in copy.schema()] == ["pcode", "name"]
    finally:
        copy.delete()  # the copy may not be created in the scratch folder
