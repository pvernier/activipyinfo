import json
from datetime import UTC, datetime

import pytest
import responses

from activipyinfo import (
    BillingAccount,
    ConfigurationError,
    Database,
    DatabaseChanges,
    Folder,
    Form,
    MultipleMatchesError,
    NoMatchError,
    NotFoundError,
    Report,
    Resource,
    ResourceType,
    SubForm,
)
from activipyinfo.ids import is_cuid

API = "https://www.activityinfo.org/resources"

SUMMARIES = [
    {
        "databaseId": "db1",
        "label": "Lebanon response",
        "description": "",
        "ownerId": "432201",
        "billingAccountId": 1025232,
        "suspended": False,
        "publishedTemplate": False,
        "languages": ["en", "ar"],
    },
    {
        "databaseId": "db2",
        "label": "Jordan response",
        "description": "Jordan",
        "ownerId": "5",
        "billingAccountId": 1,
        "suspended": True,
        "publishedTemplate": True,
        "languages": [],
    },
]

BILLING = {
    "id": 1025232,
    "code": "SUB123",
    "name": "NGO",
    "trial": False,
    "expirationTime": 1_700_000_000_000,
    "userLimit": 50,
    "fullUserLimit": 40,
    "userCount": 12,
    "databaseCount": 3,
    "status": "ACTIVE",
    "capped": True,
    "planName": "business",
    "automaticCollection": True,
    "accountCredits": 0,
    "submissionCount": 0,
    "submissionLimit": 0,
}


def sent_json(mocked, index=-1):
    return json.loads(mocked.calls[index].request.body)


@pytest.fixture
def db(client, mocked, tree_data):
    """The sample database, loaded through the client."""
    mocked.get(f"{API}/databases/db1", json=tree_data)
    database = client.databases.get("db1")
    mocked.calls.reset()
    return database


# ----------------------------------------------------------------------
# client.databases
# ----------------------------------------------------------------------


def test_list_returns_database_summaries(client, mocked):
    mocked.get(f"{API}/databases", json=SUMMARIES)

    dbs = client.databases.list()

    assert [db.id for db in dbs] == ["db1", "db2"]
    first, second = dbs
    assert first.label == "Lebanon response"
    assert first.description is None
    assert first.owner_id == "432201"
    assert first.billing_account_id == 1025232
    assert first.languages == ["en", "ar"]
    assert second.suspended is True
    assert second.published_template is True
    assert first.client is client
    assert len(mocked.calls) == 1


def test_summary_loads_tree_lazily(client, mocked, tree_data):
    mocked.get(f"{API}/databases", json=SUMMARIES)
    mocked.get(f"{API}/databases/db1", json=tree_data)
    db = client.databases.list()[0]
    assert len(mocked.calls) == 1

    assert len(db.resources) == 9
    assert db.owner.email == "owner@example.org"
    assert len(mocked.calls) == 2

    db.resources  # cached
    assert len(mocked.calls) == 2


def test_get_parses_tree(db):
    assert db.id == "db1"
    assert db.label == "Lebanon response"
    assert db.description == "Tracking the response"
    assert db.owner.id == "432201"
    assert db.owner_id == "432201"
    assert db.version == "12"
    assert db.language == "en"
    assert db.billing_plan == "business"
    assert db.role == {
        "roleId": "admin",
        "roleParameters": {},
        "roleResources": ["db1"],
    }
    assert db.raw["userId"] == "u1"


def test_get_builds_typed_resources(db):
    by_id = {r.id: r for r in db.resources}

    assert type(by_id["fadmin"]) is Folder
    assert type(by_id["fma1"]) is Form
    assert type(by_id["sfhh"]) is SubForm
    assert type(by_id["rpdash"]) is Report
    assert by_id["fma2"].visibility == "REFERENCE"
    assert by_id["fmreg"].icon == "form"
    assert by_id["fma1"].type == ResourceType.FORM
    assert all(r.database is db for r in db.resources)


def test_unknown_resource_type_is_kept(client, mocked, tree_data):
    tree_data["resources"] = [
        {"id": "x", "parentId": "db1", "label": "New thing", "type": "WIDGET"}
    ]
    mocked.get(f"{API}/databases/db1", json=tree_data)

    (resource,) = client.databases.get("db1").resources

    assert type(resource) is Resource
    assert resource.type == "WIDGET"


def test_get_unknown_database_raises(client, mocked):
    mocked.get(
        f"{API}/databases/nope",
        status=404,
        json={"code": "DATABASE_NOT_FOUND", "message": "Not found"},
    )

    with pytest.raises(NotFoundError) as info:
        client.databases.get("nope")

    assert info.value.code == "DATABASE_NOT_FOUND"


def test_find_by_label(client, mocked):
    mocked.get(f"{API}/databases", json=SUMMARIES)

    assert client.databases.find("Jordan response").id == "db2"


def test_find_by_label_without_match(client, mocked):
    mocked.get(f"{API}/databases", json=SUMMARIES)

    with pytest.raises(NoMatchError, match="Syria"):
        client.databases.find("Syria")


def test_find_by_label_with_several_matches(client, mocked):
    mocked.get(
        f"{API}/databases", json=SUMMARIES + [dict(SUMMARIES[0], databaseId="x")]
    )

    with pytest.raises(MultipleMatchesError, match="2 matches"):
        client.databases.find("Lebanon response")


def test_create_generates_id_and_returns_database(client, mocked, tree_data):
    mocked.post(f"{API}/databases", json=tree_data)

    db = client.databases.create("Lebanon response")

    payload = sent_json(mocked)
    assert is_cuid(payload.pop("id"))
    assert payload == {
        "label": "Lebanon response",
        "templateId": "",
        "description": None,
    }
    assert isinstance(db, Database)
    assert db.client is client
    assert len(db.resources) == 9


def test_create_with_explicit_id_and_description(client, mocked, tree_data):
    mocked.post(
        f"{API}/databases",
        match=[
            responses.matchers.json_params_matcher(
                {
                    "id": "mydb",
                    "label": "L",
                    "templateId": "tpl",
                    "description": "D",
                }
            )
        ],
        json=tree_data,
    )

    client.databases.create("L", description="D", template_id="tpl", id="mydb")


def test_update_posts_only_changed_parts(client, mocked, tree_data):
    mocked.post(f"{API}/databases/db1", json=tree_data)
    changes = DatabaseChanges()
    changes.delete_resource("fma1")

    db = client.databases.update("db1", changes)

    assert sent_json(mocked) == {"resourceDeletions": ["fma1"]}
    assert db.id == "db1"


def test_update_with_empty_response_refetches_tree(client, mocked, tree_data):
    mocked.post(f"{API}/databases/db1", body="")
    mocked.get(f"{API}/databases/db1", json=tree_data)

    db = client.databases.update("db1", DatabaseChanges())

    assert db.label == "Lebanon response"


def test_delete_database(client, mocked):
    mocked.delete(f"{API}/databases/db1", json={"code": "DELETED"})

    client.databases.delete("db1")

    assert mocked.calls[0].request.method == "DELETE"


def test_billing_account(client, mocked):
    mocked.get(f"{API}/databases/db1/billingAccount", json=BILLING)

    account = client.databases.billing_account("db1")

    assert isinstance(account, BillingAccount)
    assert account.id == 1025232
    assert account.plan_name == "business"
    assert account.user_count == 12
    assert account.capped is True
    assert account.expiration_time == datetime.fromtimestamp(1_700_000_000, tz=UTC)


# ----------------------------------------------------------------------
# Navigating a database
# ----------------------------------------------------------------------


def test_folders_forms_and_children(db):
    assert [f.id for f in db.folders] == ["fadmin", "farchive", "fother"]
    assert [f.id for f in db.forms] == ["fma1", "fma2", "fmreg", "fmdup"]
    assert [r.id for r in db.children] == ["fadmin", "fmreg", "fother", "rpdash"]


def test_folder_contents(db):
    admin = db.folder("fadmin")

    assert [f.id for f in admin.folders] == ["farchive"]
    assert [f.id for f in admin.forms] == ["fma1", "fma2"]
    assert [r.id for r in db.form("fma2").children] == ["sfhh"]


def test_resource_by_id(db):
    assert db.resource("fmreg").label == "Registration"

    with pytest.raises(NoMatchError):
        db.resource("missing")


def test_find_unique_label(db):
    assert db.find("Registration").id == "fmreg"


def test_find_ambiguous_label(db):
    with pytest.raises(MultipleMatchesError, match="fma1"):
        db.find("Admin1")


def test_find_narrowed_by_parent(db):
    assert db.find("Admin1", parent=db.folder("Other")).id == "fmdup"
    assert db.find("Admin1", parent="fadmin").id == "fma1"


def test_find_narrowed_by_type(db, tree_data):
    assert db.find("Dashboard", type=Report).id == "rpdash"
    assert db.find("Dashboard", type="REPORT").id == "rpdash"

    with pytest.raises(NoMatchError):
        db.find("Dashboard", type=Form)


def test_find_all_at_database_root(db):
    assert [r.id for r in db.find_all(parent=db)] == [
        "fadmin",
        "fmreg",
        "fother",
        "rpdash",
    ]


def test_folder_and_form_accept_id_or_label(db):
    assert db.folder("Archive").id == "farchive"
    assert db.folder("farchive").id == "farchive"
    assert db.form("Registration").id == "fmreg"
    assert db.form("sfhh").id == "sfhh"

    with pytest.raises(NoMatchError):
        db.folder("Registration")


def test_parent_and_path(db):
    households = db.resource("sfhh")

    assert households.parent.id == "fma2"
    assert households.path == ["Admin boundaries", "Admin2", "Households"]
    assert db.resource("fmreg").parent is db


def test_tree(db):
    assert db.tree() == "\n".join(
        [
            "Lebanon response (db1)",
            "├── Admin boundaries [folder fadmin]",
            "│   ├── Archive [folder farchive]",
            "│   ├── Admin1 [form fma1]",
            "│   └── Admin2 [form fma2]",
            "│       └── Households [subform sfhh]",
            "├── Registration [form fmreg]",
            "├── Other [folder fother]",
            "│   └── Admin1 [form fmdup]",
            "└── Dashboard [report rpdash]",
        ]
    )


def test_repr_is_short(db):
    assert repr(db) == "Database(id='db1', label='Lebanon response')"
    assert repr(db.resource("sfhh")) == "SubForm(id='sfhh', label='Households')"


def test_resources_compare_by_id(db):
    assert db.resource("fma1") == Resource("fma1", "Other label", "FORM")
    assert len({db.resource("fma1"), db.resource("fma1")}) == 1


def test_unbound_objects_raise_configuration_error():
    with pytest.raises(ConfigurationError):
        Database("db1", "Lebanon").resources

    with pytest.raises(ConfigurationError):
        Folder("f1", "Folder", "FOLDER").rename("x")


# ----------------------------------------------------------------------
# Changing a database
# ----------------------------------------------------------------------


def test_add_folder_at_root(db, mocked, tree_data):
    tree_data["resources"].append(
        {"id": "fnew", "parentId": "db1", "label": "New", "type": "FOLDER"}
    )
    mocked.post(f"{API}/databases/db1", json=tree_data)

    folder = db.add_folder("New", id="fnew")

    assert sent_json(mocked) == {
        "resourceUpdates": [
            {
                "id": "fnew",
                "parentId": "db1",
                "label": "New",
                "type": "FOLDER",
                "visibility": "PRIVATE",
            }
        ]
    }
    assert isinstance(folder, Folder)
    assert folder.database is db
    assert len(db.resources) == 10


def test_add_folder_generates_id(db, mocked, tree_data):
    def callback(request):
        entry = json.loads(request.body)["resourceUpdates"][0]
        tree_data["resources"].append(entry)
        return 200, {}, json.dumps(tree_data)

    mocked.add_callback(responses.POST, f"{API}/databases/db1", callback=callback)

    folder = db.add_folder("New")

    assert is_cuid(folder.id)


def test_add_nested_folder(db, mocked, tree_data):
    tree_data["resources"].append(
        {"id": "fsub", "parentId": "fadmin", "label": "Sub", "type": "FOLDER"}
    )
    mocked.post(f"{API}/databases/db1", json=tree_data)

    folder = db.folder("Admin boundaries").add_folder("Sub", id="fsub")

    assert sent_json(mocked)["resourceUpdates"][0]["parentId"] == "fadmin"
    assert folder.parent.id == "fadmin"


def test_rename_resource(db, mocked, tree_data):
    tree_data["resources"][2]["label"] = "Governorates"
    mocked.post(f"{API}/databases/db1", json=tree_data)
    form = db.form("fma1")

    assert form.rename("Governorates") is form

    assert sent_json(mocked) == {
        "resourceUpdates": [
            {
                "id": "fma1",
                "parentId": "fadmin",
                "label": "Governorates",
                "type": "FORM",
                "visibility": "PRIVATE",
            }
        ]
    }
    assert form.label == "Governorates"
    assert db.resource("fma1").label == "Governorates"


def test_rename_keeps_icon_and_visibility(db, mocked, tree_data):
    mocked.post(f"{API}/databases/db1", json=tree_data)

    db.form("fmreg").rename("Intake")

    entry = sent_json(mocked)["resourceUpdates"][0]
    assert entry["icon"] == "form"
    assert entry["visibility"] == "PRIVATE"


@pytest.mark.parametrize(
    ("target", "expected_parent"),
    [("root", "db1"), ("folder", "fother"), ("id", "fother")],
)
def test_move_resource(db, mocked, tree_data, target, expected_parent):
    mocked.post(f"{API}/databases/db1", json=tree_data)
    destination = {"root": db, "folder": db.folder("Other"), "id": "fother"}[target]
    form = db.form("fma1")

    form.move(destination)

    assert sent_json(mocked)["resourceUpdates"][0]["parentId"] == expected_parent
    assert form.parent_id == expected_parent


def test_move_to_folder_of_other_database_is_rejected(db, client, tree_data):
    other = Database.from_api(dict(tree_data, databaseId="db2"), client)

    with pytest.raises(ValueError, match="another database"):
        db.form("fma1").move(other.folder("Other"))


def test_delete_resource(db, mocked, tree_data):
    tree_data["resources"] = [r for r in tree_data["resources"] if r["id"] != "fma1"]
    mocked.post(f"{API}/databases/db1", json=tree_data)

    db.form("fma1").delete()

    assert sent_json(mocked) == {"resourceDeletions": ["fma1"]}
    with pytest.raises(NoMatchError):
        db.resource("fma1")


def test_apply_refreshes_database(db, mocked, tree_data):
    tree_data["languages"] = ["en", "ar", "fr"]
    mocked.post(f"{API}/databases/db1", json=tree_data)
    changes = DatabaseChanges()
    changes.add_language("fr")

    assert db.apply(changes) is db

    assert sent_json(mocked) == {"languageUpdates": ["fr"]}
    assert db.languages == ["en", "ar", "fr"]


def test_refresh(db, mocked, tree_data):
    tree_data["label"] = "Renamed elsewhere"
    mocked.get(f"{API}/databases/db1", json=tree_data)

    db.refresh()

    assert db.label == "Renamed elsewhere"


def test_database_delete_and_billing_account(db, mocked):
    mocked.delete(f"{API}/databases/db1", json={"code": "DELETED"})
    mocked.get(f"{API}/databases/db1/billingAccount", json=BILLING)

    db.delete()

    assert db.billing_account().name == "NGO"
