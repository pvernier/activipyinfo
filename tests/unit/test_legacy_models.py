"""Tests for the pre-1.0 object API (Manager, Database, Folder, Form)."""

import json
from unittest.mock import Mock

import pytest

from activipyinfo import ConfigurationError, Manager
from activipyinfo.database import Database
from activipyinfo.field import Field
from activipyinfo.folder import Folder
from activipyinfo.form import Form
from activipyinfo.record import Record

API = "https://www.activityinfo.org/resources"


def sent_json(mocked, index=-1):
    return json.loads(mocked.calls[index].request.body)


def test_manager_is_a_client_and_lists_databases(mocked):
    mocked.get(
        f"{API}/databases",
        json=[
            {"databaseId": "db1", "label": "Database 1"},
            {"databaseId": "db2", "label": "Database 2"},
        ],
    )

    manager = Manager("token_123")
    dbs = manager.get_dbs()

    assert [db.id for db in dbs] == ["db1", "db2"]
    assert [db.label for db in dbs] == ["Database 1", "Database 2"]
    assert all(db.client is manager for db in dbs)
    assert mocked.calls[0].request.headers["Authorization"] == "Bearer token_123"


def test_manager_get_db_returns_matching_database_or_none():
    manager = Manager("token_123")
    manager.get_dbs = Mock(
        return_value=[Database("db1", "Database 1"), Database("db2", "Database 2")]
    )

    assert manager.get_db("db2").id == "db2"
    assert manager.get_db("missing") is None


def test_unbound_model_raises_configuration_error():
    with pytest.raises(ConfigurationError, match="Database is not attached"):
        Database("db1", "Database 1").get_resources()


def test_database_get_resources_populates_folder_and_form_lists(client, mocked):
    mocked.get(
        f"{API}/databases/db1",
        json={
            "resources": [
                {"type": "FOLDER", "label": "Folder A", "id": "f1", "parentId": "db1"},
                {"type": "FORM", "label": "Form A", "id": "fm1", "parentId": "f1"},
            ]
        },
    )

    db = Database("db1", "Database 1", client=client)
    resources = db.get_resources()

    (folder,) = resources["folders"]
    assert isinstance(folder, Folder)
    assert folder.databaseId == "db1"
    assert folder.client is client

    (form,) = resources["forms"]
    assert isinstance(form, Form)
    assert form.databaseId == "db1"
    assert form.client is client


def test_database_get_resources_does_not_duplicate_across_calls(client, mocked):
    mocked.get(
        f"{API}/databases/db1",
        json={
            "resources": [
                {"type": "FOLDER", "label": "Folder A", "id": "f1", "parentId": "db1"},
            ]
        },
    )

    db = Database("db1", "Database 1", client=client)
    db.get_resources()
    resources = db.get_resources()

    assert len(resources["folders"]) == 1


def test_database_create_folder_posts_payload_and_returns_folder(client, mocked):
    mocked.post(f"{API}/databases/db1", json={})

    db = Database("db1", "Database 1", client=client)
    folder = db.create_folder("New Folder")

    assert isinstance(folder, Folder)
    assert folder.databaseId == "db1"
    assert folder.parentId == "db1"
    assert folder.client is client
    assert sent_json(mocked)["resourceUpdates"] == [
        {
            "id": folder.id,
            "parentId": "db1",
            "label": "New Folder",
            "type": "FOLDER",
            "visibility": "PRIVATE",
        }
    ]


def test_folder_create_form_posts_to_database_forms(client, mocked):
    mocked.post(f"{API}/databases/db1/forms", json={})
    folder = Folder("Folder", id="folder1", parentId="db1", client=client)
    folder.databaseId = "db1"

    form = folder.create_form("Admin1", [])

    assert form.parentId == "folder1"
    assert form.client is client
    assert sent_json(mocked)["formResource"]["id"] == form.id


def test_folder_delete_form_posts_resource_deletion_payload(client, mocked):
    mocked.post(f"{API}/databases/db1", json={})
    folder = Folder("Folder", id="folder1", parentId="db1", client=client)
    folder.databaseId = "db1"

    folder.delete_form(Form("Form A", id="form1"))

    payload = sent_json(mocked)
    assert payload["resourceUpdates"] == []
    assert payload["resourceDeletions"] == ["form1"]


def test_folder_delete_form_requires_database_id(client):
    folder = Folder("Folder", client=client)

    with pytest.raises(ValueError, match="databaseId must be set"):
        folder.delete_form("form1")


def test_form_get_fields_creates_field_objects_from_schema(client, mocked):
    mocked.get(
        f"{API}/form/form1/schema",
        json={
            "elements": [
                {"id": "fld1", "code": "name", "type": "FREE_TEXT"},
                {"id": "fld2", "code": "pcode", "type": "FREE_TEXT"},
            ]
        },
    )

    form = Form("Admin", id="form1", client=client)
    fields = form.get_fields()

    assert [f.id for f in fields] == ["fld1", "fld2"]
    assert [f.data["code"] for f in fields] == ["name", "pcode"]


def test_form_get_fields_does_not_duplicate_across_calls(client, mocked):
    mocked.get(
        f"{API}/form/form1/schema",
        json={"elements": [{"id": "fld1", "code": "name", "type": "FREE_TEXT"}]},
    )

    form = Form("Admin", id="form1", client=client)
    form.get_fields()

    assert len(form.get_fields()) == 1


def test_form_add_record_replaces_reference_values_and_posts_changes(client, mocked):
    mocked.get(f"{API}/form/ref_form/query", json=[{"@id": "rec_1", "pcode": "LBN001"}])
    mocked.post(f"{API}/update", json={})

    ref_form = Form("Ref", id="ref_form")
    text_field = Field(
        {"code": "name", "type": "FREE_TEXT", "key": False}, id="fld_name"
    )
    ref_field = Field(
        {"code": "admin1", "type": "reference", "key": False, "reference": ref_form},
        id="fld_ref",
    )
    record = Record([text_field, ref_field], ["Alice", "LBN001"])

    Form("Admin2", id="form2", client=client).add_record(record)

    change = sent_json(mocked)["changes"][0]
    assert change["formId"] == "form2"
    assert change["fields"] == {"fld_name": "Alice", "fld_ref": "rec_1"}
    assert record.values[1] == "rec_1"


def test_form_update_record_posts_updated_field_values(client, mocked):
    mocked.post(f"{API}/update", json={})
    field = Field({"code": "name", "type": "FREE_TEXT", "key": False}, id="fld_name")
    record = Record([field], ["Old"])

    Form("Admin", id="form1", client=client).update_record(record, ["New"])

    change = sent_json(mocked)["changes"][0]
    assert change["fields"] == {"fld_name": "New"}
    assert change["deleted"] is False


def test_form_delete_record_marks_record_as_deleted(client, mocked):
    mocked.post(f"{API}/update", json={})
    field = Field({"code": "name", "type": "FREE_TEXT", "key": False}, id="fld_name")
    record = Record([field], ["Value"])

    Form("Admin", id="form1", client=client).delete_record(record)

    change = sent_json(mocked)["changes"][0]
    assert change == {
        "formId": "form1",
        "recordId": record.id,
        "parentRecordId": None,
        "deleted": True,
        "fields": None,
    }
