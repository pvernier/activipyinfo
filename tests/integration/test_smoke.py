"""Read-only checks against the live API.

Run with: ACTIVITYINFO_TOKEN=... uv run pytest -m integration
"""

import pytest

from activipyinfo import AuthenticationError, Client, PermissionDeniedError

pytestmark = pytest.mark.integration


def test_list_databases(live_client):
    databases = live_client.get("databases")

    assert isinstance(databases, list)
    assert all("databaseId" in db for db in databases)


def test_me(live_client):
    assert live_client.me().email


def test_databases_list_and_get(live_client):
    summaries = live_client.databases.list()
    if not summaries:
        pytest.skip("the account has no database")

    db = live_client.databases.get(summaries[0].id)

    assert db.label == summaries[0].label
    assert isinstance(db.tree(), str)


def test_invalid_token_is_rejected(live_client):
    bad = Client("not-a-valid-token", base_url=live_client.base_url, max_retries=0)

    with pytest.raises(AuthenticationError):
        bad.get("databases")


def test_billing_account(live_client):
    if live_client.me().billing_account_id is None:
        pytest.skip("the user has no billing account")

    account = live_client.billing.get()

    assert account.name
    assert isinstance(live_client.billing.databases(), list)


def test_database_roles_and_users(live_client):
    summaries = live_client.databases.list()
    if not summaries:
        pytest.skip("the account has no database")
    db = summaries[0]

    assert all(role.id for role in db.roles)
    try:
        users = db.users.list()
    except PermissionDeniedError:
        pytest.skip("no permission to list users of this database")
    assert all(user.email for user in users)
