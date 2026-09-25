import pytest

from activipyinfo import (
    AttachmentField,
    CalculatedField,
    DateField,
    Form,
    FormField,
    GeoPointField,
    MonthField,
    MultilineField,
    MultiReferenceField,
    MultiSelectField,
    NoteField,
    QuantityField,
    ReferenceField,
    ReverseReferenceField,
    SectionHeader,
    SelectOption,
    SerialNumberField,
    SingleSelectField,
    SubformField,
    TextField,
    UnknownField,
    UserField,
    WeekField,
)
from activipyinfo.ids import is_cuid


def params(field):
    return field.to_api().get("typeParameters")


# ----------------------------------------------------------------------
# Common properties
# ----------------------------------------------------------------------


def test_common_properties_serialization():
    field = TextField(
        "Name",
        code="name",
        description="Full name",
        required=True,
        relevance="age > 18",
        validation="LEN(name) > 1",
        validation_message="Too short",
        required_condition="age > 60",
        hidden=True,
        hidden_in_table=True,
        id="fname",
    )

    assert field.to_api() == {
        "id": "fname",
        "code": "name",
        "label": "Name",
        "description": "Full name",
        "type": "FREE_TEXT",
        "required": True,
        "key": False,
        "relevanceCondition": "age > 18",
        "validationCondition": "LEN(name) > 1",
        "validationMessage": "Too short",
        "requiredCondition": "age > 60",
        "dataEntryVisible": False,
        "tableVisible": False,
        "typeParameters": {"barcode": False},
    }


def test_minimal_field_matches_r_defaults():
    data = DateField("Date").to_api()

    assert is_cuid(data.pop("id"))
    assert data == {
        "label": "Date",
        "type": "date",
        "required": False,
        "key": False,
        "relevanceCondition": "",
        "validationCondition": "",
        "dataEntryVisible": True,
        "tableVisible": True,
    }


def test_key_fields_are_required():
    assert TextField("Name", key=True).required is True


@pytest.mark.parametrize(
    "klass", [TextField, DateField, WeekField, MonthField, SingleSelectField]
)
def test_key_capable_types(klass):
    assert klass("X", key=True).key is True


@pytest.mark.parametrize(
    "make",
    [
        lambda: QuantityField("X", key=True),
        lambda: MultilineField("X", key=True),
        lambda: CalculatedField("X", "1", key=True),
        lambda: AttachmentField("X", key=True),
        lambda: GeoPointField("X", key=True),
        lambda: SubformField("X", "sf", key=True),
    ],
)
def test_types_that_cannot_be_keys(make):
    with pytest.raises(ValueError, match="cannot be a key field"):
        make()


@pytest.mark.parametrize("code", ["1abc", "has space", "é", "a-b", "a" * 33])
def test_invalid_codes_are_rejected(code):
    with pytest.raises(ValueError, match="field code"):
        TextField("X", code=code)


@pytest.mark.parametrize("field_id", ["1abc", "a_b", "a" * 33])
def test_invalid_ids_are_rejected(field_id):
    with pytest.raises(ValueError, match="field id"):
        TextField("X", id=field_id)


def test_fields_compare_by_content():
    assert TextField("A", id="fa") == TextField("A", id="fa")
    assert TextField("A", id="fa") != TextField("B", id="fa")
    assert TextField("A", id="fa") != DateField("A", id="fa")


def test_repr():
    assert repr(TextField("Name", code="name")) == "TextField('Name', code='name')"
    assert repr(DateField("Date")) == "DateField('Date')"


# ----------------------------------------------------------------------
# Type parameters, compared with the R package's builders
# ----------------------------------------------------------------------


def test_text_and_barcode():
    assert params(TextField("X")) == {"barcode": False}
    assert params(TextField("X", barcode=True, input_mask="000")) == {
        "inputMask": "000",
        "barcode": True,
    }


def test_quantity():
    assert params(QuantityField("X")) == {"units": "", "aggregation": "SUM"}
    assert params(QuantityField("X", units="kg", aggregation=None)) == {"units": "kg"}


def test_serial_number_is_a_required_key():
    field = SerialNumberField("No", prefix_formula='"C-"')

    assert field.key is True
    assert field.required is True
    assert params(field) == {"digits": 5, "prefixFormula": '"C-"'}


def test_calculated():
    assert params(CalculatedField("X", "a + b")) == {"formula": "a + b"}


def test_single_select():
    field = SingleSelectField("Sex", ["Female", SelectOption("Male", id="m")])

    data = params(field)
    assert data["cardinality"] == "single"
    assert data["presentation"] == "automatic"
    assert data["values"][1] == {"id": "m", "label": "Male"}
    assert is_cuid(data["values"][0]["id"])


def test_multi_select():
    assert params(MultiSelectField("Needs", ["Food"]))["cardinality"] == "multiple"


def test_select_option_lookup():
    field = SingleSelectField("Sex", [SelectOption("Female", id="f"), "Male"])

    assert field.option("Female").id == "f"
    assert field.option("f").label == "Female"
    with pytest.raises(KeyError):
        field.option("Other")


def test_select_rejects_duplicate_options():
    with pytest.raises(ValueError, match="Duplicate options"):
        SingleSelectField("Sex", ["F", "F"])


def test_select_options_accept_dicts():
    field = SingleSelectField("Sex", [{"id": "f", "label": "Female"}])

    assert field.options == [SelectOption("Female", id="f")]


def test_reference_accepts_form_objects():
    field = ReferenceField("Province", Form("cprov", "Provinces", "FORM"))

    assert field.form_id == "cprov"
    assert params(field) == {"cardinality": "single", "range": [{"formId": "cprov"}]}


def test_user_field():
    field = UserField("Owner", "db1")

    assert field.database_id == "db1"
    assert params(field) == {
        "cardinality": "single",
        "range": [{"formId": "db1@users"}],
    }


def test_multi_reference_and_reverse_reference():
    assert params(MultiReferenceField("P", "cp")) == {"range": [{"formId": "cp"}]}
    assert params(ReverseReferenceField("V", form_id="cv", field_id="fc")) == {
        "formId": "cv",
        "fieldId": "fc",
    }


def test_subform():
    field = SubformField("Members", Form("cm", "Members", "SUB_FORM"))

    assert field.subform_id == "cm"
    assert params(field) == {"formId": "cm"}


def test_geopoint():
    assert params(GeoPointField("X")) == {"manualEntryAllowed": True}
    assert params(GeoPointField("X", required_accuracy=10.0)) == {
        "requiredAccuracy": 10.0,
        "manualEntryAllowed": True,
    }


def test_attachment():
    assert params(AttachmentField("X")) == {
        "cardinality": "multiple",
        "captureMethods": ["CAMERA", "FILE", "SIGNATURE"],
    }


def test_section_and_note():
    assert params(SectionHeader("S", indentation_level=2)) == {"indentationLevel": 2}
    assert "typeParameters" not in NoteField("N").to_api()


# ----------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------


def element(field_type, **extra):
    return {"id": "f1", "label": "F", "type": field_type, **extra}


def test_parsing_tolerates_missing_properties():
    field = FormField.from_api(element("date"))

    assert type(field) is DateField
    assert field.required is False
    assert field.relevance is None
    assert field.hidden is False


def test_parsing_select_with_uppercase_cardinality():
    field = FormField.from_api(
        element(
            "enumerated",
            typeParameters={
                "cardinality": "MULTIPLE",
                "presentation": "DROPDOWN",
                "values": [{"id": "a", "label": "A"}],
            },
        )
    )

    assert type(field) is MultiSelectField
    assert field.presentation == "DROPDOWN"
    assert field.option("A").id == "a"


def test_parsing_types_is_case_insensitive():
    assert type(FormField.from_api(element("free_text"))) is TextField
    assert type(FormField.from_api(element("Narrative"))) is MultilineField


def test_parsing_keeps_key_fields_of_any_type():
    # The server's schema is authoritative, even if we would not allow it.
    field = FormField.from_api(element("quantity", key=True, required=True))

    assert field.key is True


def test_reference_with_several_forms_is_kept():
    data = element(
        "reference",
        typeParameters={
            "cardinality": "single",
            "range": [{"formId": "ca"}, {"formId": "cb"}],
        },
    )

    field = FormField.from_api(data)

    assert field.form_id == "ca"
    assert field.to_api()["typeParameters"]["range"] == [
        {"formId": "ca"},
        {"formId": "cb"},
    ]


def test_unknown_type_and_properties_round_trip():
    data = element(
        "handwriting",
        required=False,
        key=False,
        relevanceCondition="",
        validationCondition="",
        dataEntryVisible=True,
        tableVisible=True,
        typeParameters={"strokeWidth": 2},
        defaultValueFormula="TODAY()",
    )

    field = FormField.from_api(data)

    assert type(field) is UnknownField
    assert field.type == "handwriting"
    assert field.extra == {"defaultValueFormula": "TODAY()"}
    assert field.to_api() == data
