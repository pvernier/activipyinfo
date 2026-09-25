from unittest.mock import Mock, patch

from activipyinfo.database import Database
from activipyinfo.field import Field
from activipyinfo.folder import Folder
from activipyinfo.form import Form
from activipyinfo.manager import Manager
from activipyinfo.record import Record


def test_manager_get_dbs_returns_database_objects():
    with patch("activipyinfo.manager.request") as mock_request:
        response = Mock()
        response.json.return_value = [
            {"databaseId": "db1", "label": "Database 1"},
            {"databaseId": "db2", "label": "Database 2"},
        ]
        mock_request.return_value = response

        manager = Manager("token_123")
        dbs = manager.get_dbs()

    assert [db.id for db in dbs] == ["db1", "db2"]
    assert [db.label for db in dbs] == ["Database 1", "Database 2"]
    mock_request.assert_called_once_with(
        "GET",
        "https://www.activityinfo.org/resources/databases",
        headers=manager.headers,
        timeout=manager.timeout,
    )


def test_manager_get_db_returns_matching_database_or_none():
    manager = Manager("token_123")
    manager.get_dbs = Mock(
        return_value=[Database("db1", "Database 1"), Database("db2", "Database 2")]
    )

    assert manager.get_db("db2").id == "db2"
    assert manager.get_db("missing") is None


def test_database_get_resources_populates_folder_and_form_lists():
    with patch("activipyinfo.database.request") as mock_request:
        response = Mock()
        response.json.return_value = {
            "resources": [
                {"type": "FOLDER", "label": "Folder A", "id": "f1", "parentId": "db1"},
                {"type": "FORM", "label": "Form A", "id": "fm1", "parentId": "f1"},
            ]
        }
        mock_request.return_value = response

        db = Database("db1", "Database 1")
        resources = db.get_resources()

    assert len(resources["folders"]) == 1
    assert isinstance(resources["folders"][0], Folder)
    assert resources["folders"][0].databaseId == "db1"

    assert len(resources["forms"]) == 1
    assert isinstance(resources["forms"][0], Form)
    assert resources["forms"][0].databaseId == "db1"

    mock_request.assert_called_once_with(
        "GET",
        "https://www.activityinfo.org/resources/databases/db1",
        headers=db.headers,
        timeout=db.timeout,
    )


def test_database_create_folder_posts_payload_and_returns_folder():
    with patch("activipyinfo.database.request") as mock_request:
        db = Database("db1", "Database 1")
        folder = db.create_folder("New Folder")

    assert isinstance(folder, Folder)
    assert folder.databaseId == "db1"
    assert folder.parentId == "db1"

    called_url = mock_request.call_args.args[1]
    called_payload = mock_request.call_args.kwargs["json"]
    assert called_url == "https://www.activityinfo.org/resources/databases/db1"
    assert called_payload["resourceUpdates"][0]["label"] == "New Folder"


def test_folder_delete_form_posts_resource_deletion_payload():
    with patch("activipyinfo.folder.request") as mock_request:
        folder = Folder("Folder", id="folder1", parentId="db1")
        folder.databaseId = "db1"
        form = Form("Form A", id="form1")

        folder.delete_form(form)

    called_url = mock_request.call_args.args[1]
    payload = mock_request.call_args.kwargs["json"]
    assert called_url == "https://www.activityinfo.org/resources/databases/db1"
    assert payload["resourceUpdates"] == []
    assert payload["resourceDeletions"] == ["form1"]


def test_folder_delete_form_requires_database_id():
    folder = Folder("Folder")
    form = Form("Form A", id="form1")

    try:
        folder.delete_form(form)
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert str(exc) == "databaseId must be set before deleting a form."


def test_form_get_fields_creates_field_objects_from_schema():
    with patch("activipyinfo.form.request") as mock_request:
        response = Mock()
        response.json.return_value = {
            "elements": [
                {"id": "fld1", "code": "name", "type": "FREE_TEXT"},
                {"id": "fld2", "code": "pcode", "type": "FREE_TEXT"},
            ]
        }
        mock_request.return_value = response

        form = Form("Admin", id="form1")
        fields = form.get_fields()

    assert [f.id for f in fields] == ["fld1", "fld2"]
    assert [f.data["code"] for f in fields] == ["name", "pcode"]
    mock_request.assert_called_once_with(
        "GET",
        "https://www.activityinfo.org/resources/form/form1/schema",
        headers=form.headers,
        timeout=form.timeout,
    )


def test_form_add_record_replaces_reference_values_and_posts_changes():
    ref_form = Form("Ref", id="ref_form")
    text_field = Field(
        {"code": "name", "type": "FREE_TEXT", "key": False},
        id="fld_name",
    )
    ref_field = Field(
        {"code": "admin1", "type": "reference", "key": False, "reference": ref_form},
        id="fld_ref",
    )
    record = Record([text_field, ref_field], ["Alice", "LBN001"])

    with patch("activipyinfo.form.request") as mock_request:
        form = Form("Admin2", id="form2")
        form.get_form_records = Mock(return_value=[{"@id": "rec_1", "pcode": "LBN001"}])
        form.add_record(record)

    payload = mock_request.call_args.kwargs["json"]
    change = payload["changes"][0]
    assert change["formId"] == "form2"
    assert change["fields"]["fld_name"] == "Alice"
    assert change["fields"]["fld_ref"] == "rec_1"
    assert record.values[1] == "rec_1"


def test_form_update_record_posts_updated_field_values():
    field = Field({"code": "name", "type": "FREE_TEXT", "key": False}, id="fld_name")
    record = Record([field], ["Old"])

    with patch("activipyinfo.form.request") as mock_request:
        form = Form("Admin", id="form1")
        form.update_record(record, ["New"])

    payload = mock_request.call_args.kwargs["json"]
    assert payload["changes"][0]["fields"] == {"fld_name": "New"}
    assert payload["changes"][0]["deleted"] is False


def test_form_delete_record_marks_record_as_deleted():
    field = Field({"code": "name", "type": "FREE_TEXT", "key": False}, id="fld_name")
    record = Record([field], ["Value"])

    with patch("activipyinfo.form.request") as mock_request:
        form = Form("Admin", id="form1")
        form.delete_record(record)

    payload = mock_request.call_args.kwargs["json"]
    assert payload["changes"][0]["formId"] == "form1"
    assert payload["changes"][0]["recordId"] == record.id
    assert payload["changes"][0]["deleted"] is True
    assert payload["changes"][0]["fields"] is None


def test_database_get_resources_does_not_duplicate_across_calls():
    with patch("activipyinfo.database.request") as mock_request:
        response = Mock()
        response.json.return_value = {
            "resources": [
                {"type": "FOLDER", "label": "Folder A", "id": "f1", "parentId": "db1"},
            ]
        }
        mock_request.return_value = response

        db = Database("db1", "Database 1")
        db.get_resources()
        resources = db.get_resources()

    assert len(resources["folders"]) == 1


def test_form_get_fields_does_not_duplicate_across_calls():
    with patch("activipyinfo.form.request") as mock_request:
        response = Mock()
        response.json.return_value = {
            "elements": [{"id": "fld1", "code": "name", "type": "FREE_TEXT"}]
        }
        mock_request.return_value = response

        form = Form("Admin", id="form1")
        form.get_fields()
        fields = form.get_fields()

    assert len(fields) == 1
