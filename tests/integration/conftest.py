import os

import pytest

from activipyinfo import Client
from activipyinfo.client import TOKEN_ENV_VAR


@pytest.fixture(scope="session")
def live_client() -> Client:
    if not os.environ.get(TOKEN_ENV_VAR):
        pytest.skip(f"{TOKEN_ENV_VAR} is not set")
    return Client()
