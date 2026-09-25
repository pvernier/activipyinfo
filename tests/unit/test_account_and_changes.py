from datetime import UTC, datetime

from activipyinfo import DatabaseChanges, Folder, UserAccount

API = "https://www.activityinfo.org/resources"


def test_me_parses_user_account(client, mocked):
    mocked.get(
        f"{API}/accounts/status",
        json={
            "userAccount": {
                "id": 42,
                "email": "me@example.org",
                "name": "Me",
                "locale": "fr",
                "billingRole": {"billingAccountId": 7, "role": "OWNER"},
                "platformRole": "NONE",
                "activationStatus": "ACTIVE",
                "deliveryStatus": "OK",
                "idp": "",
                "locked": False,
                "provisioningStatus": "NONE",
                "billingAccount": {
                    "id": 7,
                    "name": "NGO",
                    "trial": True,
                    "expirationTime": 0,
                },
            }
        },
    )

    me = client.me()

    assert isinstance(me, UserAccount)
    assert me.id == "42"
    assert me.email == "me@example.org"
    assert me.locale == "fr"
    assert me.billing_account_id == 7
    assert me.billing_role == "OWNER"
    assert me.idp is None
    assert me.billing_account.trial is True
    assert me.billing_account.expiration_time == datetime(1970, 1, 1, tzinfo=UTC)


def test_me_without_billing_account(client, mocked):
    mocked.get(
        f"{API}/accounts/status",
        json={"userAccount": {"id": "1", "email": "a@b.c", "name": "A"}},
    )

    me = client.me()

    assert me.billing_account is None
    assert me.billing_account_id is None


def test_empty_changes():
    changes = DatabaseChanges()

    assert changes.is_empty()
    assert changes.to_api() == {}


def test_changes_serialize_all_sections():
    folder = Folder("f1", "Folder", "FOLDER", parent_id="db1")
    changes = DatabaseChanges(original_language="en")
    changes.update_resource(folder)
    changes.delete_resource(Folder("f2", "Old", "FOLDER"))
    changes.update_lock({"id": "l1"})
    changes.delete_lock("l2")
    changes.update_role({"id": "r1"})
    changes.delete_role("r2")
    changes.add_language("fr")
    changes.remove_language("ar")

    assert not changes.is_empty()
    assert changes.to_api() == {
        "resourceUpdates": [
            {
                "id": "f1",
                "parentId": "db1",
                "label": "Folder",
                "type": "FOLDER",
                "visibility": "PRIVATE",
            }
        ],
        "resourceDeletions": ["f2"],
        "lockUpdates": [{"id": "l1"}],
        "lockDeletions": ["l2"],
        "roleUpdates": [{"id": "r1"}],
        "roleDeletions": ["r2"],
        "languageUpdates": ["fr"],
        "languageDeletions": ["ar"],
        "originalLanguage": "en",
    }
