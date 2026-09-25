import os

import pytest

from activipyinfo import Client
from activipyinfo.client import TOKEN_ENV_VAR


@pytest.fixture(scope="session")
def live_client() -> Client:
    if not os.environ.get(TOKEN_ENV_VAR):
        pytest.skip(f"{TOKEN_ENV_VAR} is not set")
    return Client()


WRITES_ENV_VAR = "ACTIVITYINFO_ALLOW_WRITES"


@pytest.fixture
def scratch_database(live_client):
    """A throwaway database, deleted after the test.

    Creating databases counts against the billing account, so these tests
    only run when ACTIVITYINFO_ALLOW_WRITES=1.
    """
    if os.environ.get(WRITES_ENV_VAR) != "1":
        pytest.skip(f"set {WRITES_ENV_VAR}=1 to run tests that create databases")
    db = live_client.databases.create("activipyinfo integration test (safe to delete)")
    try:
        yield db
    finally:
        db.delete()
