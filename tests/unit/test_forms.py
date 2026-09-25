import json

import pytest
import responses

from activipyinfo import (
    BadRequestError,
    FormSchema,
    QuantityField,
    SubForm,
    SubformField,
    TextField,
)

API = "https://www.activityinfo.org/resources"


def sent_json(mocked, index=-1):
    return json.loads(mocked.calls[index].request.body)


def schema_data(form_id="fma1", label="Admin1", elements=None, **extra):
    return {
        "id": form_id,
        "label": label,
        "databaseId": "db1",
        "schemaVersion": 3,
        "elements": (
            elements
            if elements is not None
            else [TextField("P-code", code="pcode", key=True, id="fpcode").to_api()]
        ),
        **extra,
    }


@pytest.fixture
def db(client, mocked, tree_data):
    mocked.get(f"{API}/databases/db1", json=tree_data)
    database = client.databases.get("db1")
    mocked.calls.reset()
    return database


def with_resource(tree_data, **resource):
    tree = dict(tree_data)
    tree["resources"] = [*tree_data["resources"], resource]
    return tree


# ----------------------------------------------------------------------
# client.forms
# ----------------------------------------------------------------------


def test_get_schema(client, mocked):
    mocked.get(f"{API}/form/fma1/schema", json=schema_data())

    schema = client.forms.get_schema("fma1")

    assert schema.id == "fma1"
    assert schema.schema_version == 3
    assert schema["pcode"].key is True


def test_add_payload_matches_r_package(client, mocked):
    schema = FormSchema("Admin1", [TextField("P-code", id="fpcode")], id="cnew")
    schema.database_id = "db1"
    mocked.post(
        f"{API}/databases/db1/forms",
        json={"forms": [{"id": "cnew", "schema": schema.to_api()}]},
    )

    added = client.forms.add(schema, parent_id="fadmin")

    assert sent_json(mocked) == {
        "formResource": {
            "id": "cnew",
            "parentId": "fadmin",
            "type": "FORM",
            "label": "Admin1",
            "visibility": "PRIVATE",
        },
        "formClass": schema.to_api(),
    }
    assert added.id == "cnew"
    assert len(mocked.calls) == 1


def test_add_defaults_to_database_root(client, mocked):
    schema = FormSchema("F", id="cnew", database_id="db1")
    mocked.post(f"{API}/databases/db1/forms", json=schema.to_api())

    client.forms.add(schema)

    assert sent_json(mocked)["formResource"]["parentId"] == "db1"


def test_add_subform_uses_parent_form(client, mocked):
    schema = FormSchema("Members", id="cm", database_id="db1", parent_form_id="fma2")
    mocked.post(f"{API}/databases/db1/forms", json=schema.to_api())

    client.forms.add(schema, parent_id="fadmin")

    assert sent_json(mocked)["formResource"]["parentId"] == "fma2"
    assert sent_json(mocked)["formClass"]["parentFormId"] == "fma2"


def test_add_requires_database_id(client):
    with pytest.raises(ValueError, match="database_id"):
        client.forms.add(FormSchema("F"))


def test_response_without_schema_refetches_it(client, mocked):
    schema = FormSchema("F", id="cnew", database_id="db1")
    mocked.post(f"{API}/databases/db1/forms", json={"databaseId": "db1"})
    mocked.get(f"{API}/form/cnew/schema", json=schema_data("cnew", "F"))

    assert client.forms.add(schema).label == "F"


def test_update_schema(client, mocked):
    schema = FormSchema.from_api(schema_data())
    schema.add_field(QuantityField("Population", code="pop", id="fpop"))
    mocked.post(
        f"{API}/form/fma1/schema",
        json={"forms": [{"id": "fma1", "schema": schema.to_api()}]},
    )

    updated = client.forms.update_schema(schema)

    assert sent_json(mocked)["schemaVersion"] == 3
    assert [e["id"] for e in sent_json(mocked)["elements"]] == ["fpcode", "fpop"]
    assert updated["pop"].id == "fpop"


def test_schema_version_recover_relocate(client, mocked):
    mocked.get(f"{API}/form/fma1/schema/versions/2", json=schema_data())
    mocked.post(f"{API}/form/fma1/field/fold/recover", json={"databaseId": "db1"})
    mocked.get(f"{API}/form/fma1/schema", json=schema_data())
    mocked.post(
        f"{API}/form/fma1/database",
        match=[responses.matchers.json_params_matcher({"databaseId": "db2"})],
        json={"code": "RELOCATED"},
    )

    assert client.forms.schema_version("fma1", 2).id == "fma1"
    assert client.forms.recover_field("fma1", "fold").id == "fma1"
    client.forms.relocate("fma1", "db2")


# ----------------------------------------------------------------------
# db.add_form / folder.add_form
# ----------------------------------------------------------------------


def test_db_add_form_from_label_and_fields(db, mocked, tree_data):
    def add(request):
        schema = json.loads(request.body)["formClass"]
        add.form_id = schema["id"]
        return 200, {}, json.dumps({"forms": [{"id": schema["id"], "schema": schema}]})

    mocked.add_callback(responses.POST, f"{API}/databases/db1/forms", callback=add)
    mocked.add_callback(
        responses.GET,
        f"{API}/databases/db1",
        callback=lambda request: (
            200,
            {},
            json.dumps(
                with_resource(
                    tree_data,
                    id=add.form_id,
                    parentId="db1",
                    label="Households",
                    type="FORM",
                )
            ),
        ),
    )

    form = db.add_form("Households", [TextField("Head", code="head", key=True)])

    payload = sent_json(mocked, 0)
    assert payload["formClass"]["databaseId"] == "db1"
    assert payload["formClass"]["label"] == "Households"
    assert payload["formClass"]["elements"][0]["code"] == "head"
    assert payload["formResource"]["parentId"] == "db1"
    assert form.label == "Households"
    assert form.database is db


def test_folder_add_form(db, mocked, tree_data):
    schema = FormSchema("Villages", id="cvil")
    mocked.post(f"{API}/databases/db1/forms", json=schema.to_api())
    mocked.get(
        f"{API}/databases/db1",
        json=with_resource(
            tree_data, id="cvil", parentId="fadmin", label="Villages", type="FORM"
        ),
    )

    form = db.folder("Admin boundaries").add_form(schema)

    assert sent_json(mocked, 0)["formResource"]["parentId"] == "fadmin"
    assert form.parent.id == "fadmin"


def test_add_form_rejects_fields_with_schema(db):
    with pytest.raises(ValueError, match="in the FormSchema"):
        db.add_form(FormSchema("F"), [TextField("X")])


# ----------------------------------------------------------------------
# Form methods
# ----------------------------------------------------------------------


def test_form_schema(db, mocked):
    mocked.get(f"{API}/form/fma1/schema", json=schema_data())

    assert db.form("fma1").schema()["pcode"].key is True


def test_form_add_field(db, mocked):
    mocked.get(f"{API}/form/fma1/schema", json=schema_data())

    def update(request):
        return 200, {}, request.body

    mocked.add_callback(responses.POST, f"{API}/form/fma1/schema", callback=update)

    added = db.form("fma1").add_field(
        TextField("Name", code="name", id="fname"), after="pcode"
    )

    assert [e["id"] for e in sent_json(mocked)["elements"]] == ["fpcode", "fname"]
    assert added.code == "name"


def test_form_delete_field(db, mocked):
    elements = [
        TextField("P-code", code="pcode", key=True, id="fpcode").to_api(),
        TextField("Name", code="name", id="fname").to_api(),
    ]
    mocked.get(f"{API}/form/fma1/schema", json=schema_data(elements=elements))
    mocked.post(f"{API}/form/fma1/schema", json=schema_data())

    removed = db.form("fma1").delete_field("name")

    assert removed.id == "fname"
    assert [e["id"] for e in sent_json(mocked)["elements"]] == ["fpcode"]


def test_update_schema_of_another_form_is_rejected(db):
    with pytest.raises(ValueError, match="is not the schema"):
        db.form("fma1").update_schema(FormSchema("X", id="other"))


def test_renaming_through_schema_refreshes_database(db, mocked, tree_data):
    renamed = schema_data(label="Governorates")
    mocked.post(f"{API}/form/fma1/schema", json=renamed)
    tree_data["resources"][2]["label"] = "Governorates"
    mocked.get(f"{API}/databases/db1", json=tree_data)

    db.form("fma1").update_schema(FormSchema.from_api(renamed))

    assert db.resource("fma1").label == "Governorates"


def subform_tree(tree_data, subform_id="cm"):
    return with_resource(
        tree_data, id=subform_id, parentId="fma1", label="Members", type="SUB_FORM"
    )


def test_add_subform_links_parent_first(db, mocked, tree_data):
    # The server requires the parent's subform field before the subform.
    mocked.get(f"{API}/form/fma1/schema", json=schema_data())
    mocked.post(f"{API}/form/fma1/schema", json=schema_data())
    mocked.post(
        f"{API}/form/cm/schema",
        json=schema_data("cm", "Members", elements=[], parentFormId="fma1"),
    )
    mocked.get(f"{API}/databases/db1", json=subform_tree(tree_data))

    subform = db.form("fma1").add_subform(
        FormSchema("Members", [TextField("Name")], id="cm")
    )

    calls = [(c.request.method, c.request.url) for c in mocked.calls]
    assert calls == [
        ("GET", f"{API}/form/fma1/schema"),
        ("POST", f"{API}/form/fma1/schema"),
        ("POST", f"{API}/form/cm/schema"),
        ("GET", f"{API}/databases/db1"),
    ]
    link = sent_json(mocked, 1)["elements"][-1]
    assert link["type"] == "subform"
    assert link["label"] == "Members"
    assert link["typeParameters"] == {"formId": "cm"}
    saved = sent_json(mocked, 2)
    assert saved["parentFormId"] == "fma1"
    assert saved["databaseId"] == "db1"
    assert isinstance(subform, SubForm)


def test_add_subform_creates_it_if_the_server_did_not(db, mocked, tree_data):
    mocked.get(f"{API}/form/fma1/schema", json=schema_data())
    mocked.post(f"{API}/form/fma1/schema", json=schema_data())
    mocked.post(f"{API}/form/cm/schema", status=404, json={"code": "FORM_NOT_FOUND"})
    mocked.post(
        f"{API}/databases/db1/forms",
        json=schema_data("cm", "Members", elements=[], parentFormId="fma1"),
    )
    mocked.get(f"{API}/databases/db1", json=subform_tree(tree_data))

    db.form("fma1").add_subform(FormSchema("Members", id="cm"))

    created = sent_json(mocked, 3)
    assert created["formResource"]["parentId"] == "fma1"
    assert created["formClass"]["parentFormId"] == "fma1"


def test_add_subform_removes_the_link_if_it_fails(db, mocked):
    parent = schema_data()
    mocked.get(f"{API}/form/fma1/schema", json=parent)
    mocked.post(f"{API}/form/fma1/schema", json=parent)
    mocked.post(
        f"{API}/form/cm/schema",
        status=400,
        json={"code": "INVALID_SCHEMA", "message": "Bad subform"},
    )
    linked = schema_data(
        elements=[
            *parent["elements"],
            SubformField("Members", "cm", id="flink").to_api(),
        ]
    )
    mocked.get(f"{API}/form/fma1/schema", json=linked)
    mocked.post(f"{API}/form/fma1/schema", json=parent)

    with pytest.raises(BadRequestError, match="Bad subform"):
        db.form("fma1").add_subform(FormSchema("Members", id="cm"))

    rollback = sent_json(mocked)
    assert [e["id"] for e in rollback["elements"]] == ["fpcode"]


def test_add_subform_reuses_an_existing_link(db, mocked, tree_data):
    linked = schema_data(elements=[SubformField("Members", "cm", id="fsub").to_api()])
    mocked.get(f"{API}/form/fma1/schema", json=linked)
    mocked.post(f"{API}/form/cm/schema", json=schema_data("cm", "Members"))
    mocked.get(f"{API}/databases/db1", json=subform_tree(tree_data))

    db.form("fma1").add_subform(FormSchema("Members", [TextField("Name")], id="cm"))

    assert [c.request.method for c in mocked.calls] == ["GET", "POST", "GET"]


def test_relocate_refreshes_database(db, mocked, tree_data):
    mocked.post(f"{API}/form/fma1/database", json={"code": "RELOCATED"})
    tree_data["resources"] = [r for r in tree_data["resources"] if r["id"] != "fma1"]
    mocked.get(f"{API}/databases/db1", json=tree_data)

    db.form("fma1").relocate("db2")

    assert "fma1" not in [r.id for r in db.resources]


def test_duplicate_returns_the_copy(db, mocked, tree_data):
    mocked.post(
        f"{API}/databases/db1/forms/fma1/duplicate",
        json=with_resource(
            tree_data, id="ccopy", parentId="fadmin", label="Admin1 (copy)", type="FORM"
        ),
    )

    copy = db.form("fma1").duplicate()

    assert copy.id == "ccopy"
    assert copy.database is db


def test_recover_field_and_schema_version(db, mocked):
    mocked.post(
        f"{API}/form/fma1/field/fold/recover",
        json={"forms": [{"id": "fma1", "schema": schema_data()}]},
    )
    mocked.get(f"{API}/form/fma1/schema/versions/1", json=schema_data())

    assert db.form("fma1").recover_field("fold").id == "fma1"
    assert db.form("fma1").schema_version(1).schema_version == 3
