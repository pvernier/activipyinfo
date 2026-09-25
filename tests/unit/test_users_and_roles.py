import json
from datetime import UTC, date, datetime

import pytest
import responses

from activipyinfo import (
    DatabaseUser,
    Grant,
    MultipleMatchesError,
    NoMatchError,
    Operation,
    Permission,
    Role,
    resource_permissions,
)

API = "https://www.activityinfo.org/resources"
USERS = f"{API}/databases/db1/users"

ALICE = {
    "databaseId": "db1",
    "userId": "101",
    "name": "Alice",
    "email": "Alice@Example.org",
    "version": 3,
    "inviteDate": "2026-01-15",
    "deliveryStatus": "OK",
    "inviteAccepted": True,
    "locked": False,
    "userLicenseType": "FULL",
    "lastLoginDate": "2026-09-01",
    "activationStatus": "ACTIVE",
    "role": {"id": "readonly", "parameters": {}, "resources": ["db1"]},
}
BOB = {
    "databaseId": "db1",
    "userId": "102",
    "name": "Bob",
    "email": "bob@example.org",
    "role": {
        "id": "dataentry",
        "parameters": {"partner": "p1"},
        "resources": ["fadmin"],
    },
}
BOB_GRANTS = {
    **BOB,
    "inviteTime": 1_700_000_000_000,
    "lastLoginTime": 1_700_000_000,
    "grants": [{"resourceId": "fma1", "operations": ["VIEW"], "locked": False}],
}


def sent_json(mocked, index=-1):
    return json.loads(mocked.calls[index].request.body)


@pytest.fixture
def db(client, mocked, tree_data):
    mocked.get(f"{API}/databases/db1", json=tree_data)
    database = client.databases.get("db1")
    mocked.calls.reset()
    return database


# ----------------------------------------------------------------------
# DatabaseUser parsing
# ----------------------------------------------------------------------


def test_database_user_from_list_endpoint():
    user = DatabaseUser.from_api(ALICE)

    assert user.user_id == "101"
    assert user.role.role_id == "readonly"
    assert user.role.resources == ["db1"]
    assert user.invite_time == date(2026, 1, 15)
    assert user.last_login_time == date(2026, 9, 1)
    assert user.user_license_type == "FULL"
    assert user.invite_accepted is True
    assert repr(user) == "DatabaseUser(email='Alice@Example.org', role='readonly')"


def test_database_user_from_grants_endpoint():
    user = DatabaseUser.from_api(BOB_GRANTS)

    assert user.role.parameters == {"partner": "p1"}
    assert user.grants[0].operations == [Operation.VIEW]
    # Milliseconds and seconds since the epoch are both accepted.
    assert user.invite_time == datetime.fromtimestamp(1_700_000_000, tz=UTC)
    assert user.last_login_time == user.invite_time


def test_database_users_compare_by_database_and_id():
    assert DatabaseUser.from_api(ALICE) == DatabaseUser.from_api(dict(ALICE, name="A"))
    assert DatabaseUser.from_api(ALICE) != DatabaseUser.from_api(BOB)


# ----------------------------------------------------------------------
# client.users
# ----------------------------------------------------------------------


def test_list_users(client, mocked):
    mocked.get(USERS, json=[ALICE, BOB])

    users = client.users.list("db1")

    assert [u.email for u in users] == ["Alice@Example.org", "bob@example.org"]
    assert users[0].client is client


def test_get_user_uses_grants_endpoint(client, mocked):
    mocked.get(f"{USERS}/102/grants", json=BOB_GRANTS)

    assert client.users.get("db1", "102").grants[0].resource_id == "fma1"


def test_users_on_resource(client, mocked):
    mocked.get(f"{API}/databases/db1/resources/fma1/grants", json=[BOB_GRANTS])

    assert [u.user_id for u in client.users.on_resource("db1", "fma1")] == ["102"]


def test_add_user_payload_matches_r_package(client, mocked):
    mocked.post(USERS, json=BOB)

    user = client.users.add(
        "db1",
        "bob@example.org",
        "Bob",
        Role("Data entry"),
        resources=["fadmin"],
        parameters={"partner": "p1"},
        locale="fr",
    )

    assert sent_json(mocked) == {
        "email": "bob@example.org",
        "name": "Bob",
        "locale": "fr",
        "role": {
            "id": "dataentry",
            "parameters": {"partner": "p1"},
            "resources": ["fadmin"],
        },
        "grants": [],
    }
    assert user.user_id == "102"


def test_add_user_defaults_to_whole_database(client, mocked):
    mocked.post(USERS, json=ALICE)

    client.users.add("db1", "alice@example.org", "Alice", "readonly")

    assert sent_json(mocked)["role"] == {
        "id": "readonly",
        "parameters": {},
        "resources": ["db1"],
    }
    assert sent_json(mocked)["locale"] == "en"


def test_set_role(client, mocked):
    mocked.post(f"{USERS}/101/role", json=ALICE)

    client.users.set_role("db1", "101", "dataentry", parameters={"partner": "p2"})

    assert sent_json(mocked) == {
        "assignments": [
            {"id": "dataentry", "parameters": {"partner": "p2"}, "resources": ["db1"]}
        ]
    }


def test_set_role_with_empty_response_refetches_user(client, mocked):
    mocked.post(f"{USERS}/102/role", body="")
    mocked.get(f"{USERS}/102/grants", json=BOB_GRANTS)

    assert client.users.set_role("db1", "102", "dataentry").user_id == "102"


def test_update_grants(client, mocked):
    mocked.post(f"{USERS}/102/grants", json=BOB_GRANTS)

    client.users.update_grants(
        "db1",
        "102",
        add=[Grant("fma1", resource_permissions(edit_record="x == 1"))],
        remove=["fma2"],
    )

    assert sent_json(mocked) == {
        "roleUpdates": [],
        "grantUpdates": [{"resourceId": "fma1", "operations": ["VIEW", "EDIT_RECORD"]}],
        "grantDeletions": ["fma2"],
    }


def test_remove_unlock_and_restore(client, mocked):
    mocked.delete(f"{USERS}/101")
    mocked.post(f"{USERS}/101/unlock")
    mocked.post(
        f"{USERS}/101/restore",
        json={"revertedAuditLogEventId": "e1", "restoredUser": ALICE},
    )

    client.users.remove("db1", "101")
    client.users.unlock("db1", "101")
    restored = client.users.restore("db1", "101")

    assert [c.request.method for c in mocked.calls] == ["DELETE", "POST", "POST"]
    assert restored.email == "Alice@Example.org"


def test_database_user_methods(client, mocked):
    mocked.get(USERS, json=[BOB])
    mocked.post(f"{USERS}/102/role", json=BOB)
    mocked.post(f"{USERS}/102/unlock")
    mocked.delete(f"{USERS}/102")
    bob = client.users.list("db1")[0]

    bob.set_role("readonly")
    bob.unlock()
    bob.remove()

    assert [c.request.url for c in mocked.calls[1:]] == [
        f"{USERS}/102/role",
        f"{USERS}/102/unlock",
        f"{USERS}/102",
    ]


# ----------------------------------------------------------------------
# db.users
# ----------------------------------------------------------------------


def test_db_users_find_by_email_case_insensitively(db, mocked):
    mocked.get(USERS, json=[ALICE, BOB])
    mocked.get(f"{USERS}/101/grants", json=ALICE)

    assert db.users.get("alice@example.ORG").user_id == "101"


def test_db_users_unknown_email(db, mocked):
    mocked.get(USERS, json=[ALICE])

    with pytest.raises(NoMatchError, match="nobody@example.org"):
        db.users.remove("nobody@example.org")


def test_db_users_accept_ids_and_objects(db, mocked):
    mocked.delete(f"{USERS}/101")
    mocked.delete(f"{USERS}/102")

    db.users.remove("101")
    db.users.remove(DatabaseUser.from_api(BOB))

    assert len(mocked.calls) == 2


def test_db_users_add_resolves_role_label(db, mocked):
    mocked.post(USERS, json=BOB)

    db.users.add(
        "bob@example.org",
        "Bob",
        "Data entry",
        resources=[db.folder("Admin boundaries")],
        parameters={"partner": "p1"},
    )

    assert sent_json(mocked)["role"] == {
        "id": "dataentry",
        "parameters": {"partner": "p1"},
        "resources": ["fadmin"],
    }


def test_db_users_add_passes_unknown_role_id_through(db, mocked):
    mocked.post(USERS, json=ALICE)

    db.users.add("a@example.org", "A", "builtinrole")

    assert sent_json(mocked)["role"]["id"] == "builtinrole"


def test_db_users_set_role_by_email(db, mocked):
    mocked.get(USERS, json=[ALICE, BOB])
    mocked.post(f"{USERS}/102/role", json=BOB)

    db.users.set_role("bob@example.org", "Read only")

    assert sent_json(mocked)["assignments"][0]["id"] == "readonly"


def test_db_users_other_methods(db, mocked):
    mocked.get(USERS, json=[ALICE])
    mocked.get(f"{API}/databases/db1/resources/fma1/grants", json=[])
    mocked.post(f"{USERS}/101/grants", json=ALICE)
    mocked.post(f"{USERS}/101/unlock")
    mocked.post(f"{USERS}/101/restore", json={"restoredUser": ALICE})

    assert [u.user_id for u in db.users.list()] == ["101"]
    assert db.users.on_resource(db.form("fma1")) == []
    db.users.update_grants("101", remove=[db.form("fma1")])
    db.users.unlock("101")
    assert db.users.restore("101").user_id == "101"

    assert sent_json(mocked, 2)["grantDeletions"] == ["fma1"]


# ----------------------------------------------------------------------
# db.roles
# ----------------------------------------------------------------------


def test_roles_are_parsed_from_tree(db):
    roles = db.roles

    assert len(roles) == 2
    assert [r.id for r in roles] == ["readonly", "dataentry"]
    assert roles[0].label == "Read only"
    assert roles[0].grants[0].operations == [Operation.VIEW, Operation.EXPORT_RECORDS]

    data_entry = roles[1]
    assert data_entry.permissions == [Permission(Operation.MANAGE_USERS)]
    assert data_entry.parameters[0].range == "fma1"
    grant = data_entry.grant_for("fadmin")
    assert grant.optional is True
    assert grant.permissions[1] == Permission(
        Operation.EDIT_RECORD,
        filter="[partner] == @user.partner",
        security_categories=("reviewer",),
    )


def test_roles_get_by_id_or_label(db):
    assert db.roles.get("readonly").label == "Read only"
    assert db.roles.get("Data entry").id == "dataentry"

    with pytest.raises(NoMatchError):
        db.roles.get("Admin")


def test_roles_get_ambiguous_label(db, tree_data, client, mocked):
    tree_data["roles"].append(dict(tree_data["roles"][0], id="readonly2"))
    mocked.get(f"{API}/databases/db1", json=tree_data)

    with pytest.raises(MultipleMatchesError):
        client.databases.get("db1").roles.get("Read only")


def test_roles_load_tree_lazily(client, mocked, tree_data):
    mocked.get(
        f"{API}/databases",
        json=[{"databaseId": "db1", "label": "Lebanon response"}],
    )
    mocked.get(f"{API}/databases/db1", json=tree_data)

    db = client.databases.list()[0]

    assert len(db.roles) == 2


def test_add_role(db, mocked, tree_data):
    role = Role("Viewer", grants=[Grant("db1")])
    tree_data["roles"].append(role.to_api())
    mocked.post(f"{API}/databases/db1", json=tree_data)

    added = db.roles.add(role)

    assert sent_json(mocked) == {"roleUpdates": [role.to_api()]}
    assert added.id == "viewer"
    assert len(db.roles) == 3


def test_add_existing_role_is_rejected(db):
    with pytest.raises(ValueError, match="already exists"):
        db.roles.add(Role("Read only", id="readonly"))


def test_update_role(db, mocked, tree_data):
    tree_data["roles"][0]["label"] = "Viewers"
    mocked.post(f"{API}/databases/db1", json=tree_data)
    role = db.roles.get("readonly")
    role.label = "Viewers"

    assert db.roles.update(role).label == "Viewers"
    assert sent_json(mocked)["roleUpdates"][0]["id"] == "readonly"


def test_delete_role_by_label(db, mocked, tree_data):
    tree_data["roles"] = tree_data["roles"][1:]
    mocked.post(
        f"{API}/databases/db1",
        match=[responses.matchers.json_params_matcher({"roleDeletions": ["readonly"]})],
        json=tree_data,
    )

    db.roles.delete("Read only")

    assert [r.id for r in db.roles] == ["dataentry"]
