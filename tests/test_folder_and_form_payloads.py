from activipyinfo.field import Field
from activipyinfo.folder import Folder
from activipyinfo.form import Form


def test_folder_build_payload_contains_resource_update_and_attributes():
    folder = Folder("Admin")
    folder.parentId = "db_1"

    payload = folder.build_payload()

    assert "resourceUpdates" in payload
    assert payload["resourceUpdates"][0]["id"] == folder.id
    assert payload["resourceUpdates"][0]["parentId"] == "db_1"
    assert payload["resourceUpdates"][0]["label"] == "Admin"
    assert payload["resourceUpdates"][0]["type"] == "FOLDER"
    assert payload["resourceUpdates"][0]["visibility"] == "PRIVATE"
    assert "token" not in payload
    assert "headers" not in payload
    assert "base_url" not in payload


def test_form_build_payload_for_regular_and_reference_fields():
    reference_form = Form("Admin1", id="form_ref")
    regular_field = Field(
        {
            "code": "name",
            "label": "Name",
            "description": "desc",
            "required": True,
            "type": "FREE_TEXT",
            "key": False,
        },
        id="field_name",
    )
    reference_field = Field(
        {
            "code": "admin1",
            "label": "Admin1",
            "description": "desc",
            "required": True,
            "type": "reference",
            "key": False,
            "reference": reference_form,
        },
        id="field_ref",
    )

    form = Form("Admin2", fields=[regular_field, reference_field], id="form_2", parentId="folder_1")
    form.databaseId = "db_1"

    payload = form.build_payload()

    assert payload["formResource"]["id"] == "form_2"
    assert payload["formResource"]["parentId"] == "folder_1"
    assert payload["formClass"]["databaseId"] == "db_1"

    elements = payload["formClass"]["elements"]
    assert len(elements) == 2

    first = elements[0]
    assert first["id"] == "field_name"
    assert first["typeParameters"] == {"barcode": False}
    assert "key" not in first

    second = elements[1]
    assert second["id"] == "field_ref"
    assert second["typeParameters"] == {
        "cardinality": "single",
        "range": [{"formId": "form_ref"}],
    }
    assert "reference" not in second
    assert "key" not in second
