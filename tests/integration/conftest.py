import os
from dataclasses import dataclass

import pytest

from activipyinfo import BadRequestError, Client, Database, Folder, cuid
from activipyinfo.client import TOKEN_ENV_VAR

WRITES_ENV_VAR = "ACTIVITYINFO_ALLOW_WRITES"
DATABASE_ENV_VAR = "ACTIVITYINFO_TEST_DATABASE"


@pytest.fixture(scope="session")
def live_client() -> Client:
    if not os.environ.get(TOKEN_ENV_VAR):
        pytest.skip(f"{TOKEN_ENV_VAR} is not set")
    return Client()


@dataclass
class Sandbox:
    """Where a write test may create things: a scratch folder of ``db``."""

    db: Database
    folder: Folder


@pytest.fixture
def sandbox(live_client):
    """A scratch folder, deleted (with everything in it) after the test.

    Write tests only run when ACTIVITYINFO_ALLOW_WRITES=1. The folder is
    created in the database named by ACTIVITYINFO_TEST_DATABASE, or else in a
    new database, which needs an account allowed to create databases.
    Anything a test creates outside the folder (roles, users) must be
    cleaned up by the test itself.
    """
    if os.environ.get(WRITES_ENV_VAR) != "1":
        pytest.skip(f"set {WRITES_ENV_VAR}=1 to run tests that change data")

    database_id = os.environ.get(DATABASE_ENV_VAR)
    created_database = False
    if database_id:
        db = live_client.databases.get(database_id)
    else:
        try:
            db = live_client.databases.create(
                "activipyinfo integration test (safe to delete)"
            )
        except BadRequestError as exc:
            if exc.code != "NO_BILLING_ACCOUNT":
                raise
            pytest.skip(
                f"this account cannot create databases; set {DATABASE_ENV_VAR} "
                "to the id of a database where you can add folders and forms"
            )
        created_database = True

    folder = db.add_folder(f"activipyinfo test {cuid()[:8]} (safe to delete)")
    try:
        yield Sandbox(db, folder)
    finally:
        if created_database:
            db.delete()
        else:
            db.refresh().resource(folder.id).delete()
