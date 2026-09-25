import pytest
import responses as responses_lib

from activipyinfo.client import BASE_URL_ENV_VAR, TOKEN_ENV_VAR


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    """Unit tests must never pick up a real token or server from the environment."""
    monkeypatch.delenv(TOKEN_ENV_VAR, raising=False)
    monkeypatch.delenv(BASE_URL_ENV_VAR, raising=False)


@pytest.fixture
def mocked():
    """Intercept all HTTP calls; fails the test if a registered call is unused."""
    with responses_lib.RequestsMock() as rsps:
        yield rsps
