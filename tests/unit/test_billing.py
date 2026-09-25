from datetime import date

import pytest
import responses

from activipyinfo import ConfigurationError

API = "https://www.activityinfo.org/resources"
ACCOUNT = {"id": 7, "name": "NGO", "planName": "business", "status": "ACTIVE"}


def me(billing_account_id):
    return {
        "userAccount": {
            "id": "1",
            "email": "me@example.org",
            "name": "Me",
            "billingAccountId": billing_account_id,
        }
    }


def test_get_explicit_account(client, mocked):
    mocked.get(f"{API}/billingAccounts/7", json=ACCOUNT)

    account = client.billing.get(7)

    assert account.name == "NGO"
    assert account.status == "ACTIVE"


def test_account_defaults_to_current_user(client, mocked):
    mocked.get(f"{API}/accounts/status", json=me(7))
    mocked.get(f"{API}/billingAccounts/7", json=ACCOUNT)

    assert client.billing.get().id == 7


def test_user_without_billing_account(client, mocked):
    mocked.get(f"{API}/accounts/status", json=me(None))

    with pytest.raises(ValueError, match="no billing account"):
        client.billing.get()


def test_default_account_with_personal_api_token(client, mocked):
    mocked.get(
        f"{API}/accounts/status",
        status=403,
        json={
            "code": "FORBIDDEN",
            "message": "This request cannot be taken with an API token",
        },
    )

    with pytest.raises(ConfigurationError, match="Pass account_id"):
        client.billing.databases()


def test_users(client, mocked):
    mocked.get(
        f"{API}/billingAccounts/7/users",
        match=[
            responses.matchers.query_param_matcher(
                {"owners": "false", "databaseId": "db1"}
            )
        ],
        json=[
            {
                "userId": 5,
                "email": "a@example.org",
                "name": "A",
                "billingAccountRole": "NONE",
                "userLicenseType": "BASIC",
                "lastLoginTime": 1_700_000_000_000,
            }
        ],
    )

    (user,) = client.billing.users(7, owners_only=False, database_id="db1")

    assert user.user_id == "5"
    assert user.user_license_type == "BASIC"
    assert user.last_login_time.year == 2023


def test_users_without_filters_sends_no_params(client, mocked):
    mocked.get(
        f"{API}/billingAccounts/7/users",
        match=[responses.matchers.query_string_matcher("")],
        json=[],
    )

    assert client.billing.users(7) == []


def test_databases(client, mocked):
    mocked.get(
        f"{API}/billingAccounts/7/databases",
        json=[
            {
                "databaseId": "db1",
                "label": "Lebanon",
                "description": "",
                "owner": {"id": 3, "name": "O", "email": "o@example.org"},
                "formCount": 4,
                "userCount": 10,
                "basicUserCount": 2,
                "recordCount": 1234,
                "lastRecordUpdate": "2026-09-20",
                "billingAccountId": 7,
                "suspended": False,
                "publishedTemplate": False,
            }
        ],
    )

    (db,) = client.billing.databases(7)

    assert db.database_id == "db1"
    assert db.description is None
    assert db.owner_id == "3"
    assert db.owner_email == "o@example.org"
    assert db.record_count == 1234
    assert db.last_record_update == date(2026, 9, 20)


def test_domains(client, mocked):
    mocked.get(
        f"{API}/billingAccounts/7/domains",
        json=[{"domain": "example.org", "deliveryStatus": "OK", "userCount": 12}],
    )

    (domain,) = client.billing.domains(7)

    assert domain.domain == "example.org"
    assert domain.idp is None
    assert domain.user_count == 12
