import pytest

from activipyinfo import Client


@pytest.fixture
def client() -> Client:
    """A client whose retries do not sleep."""
    c = Client("test-token", backoff_factor=0)
    c._sleep = lambda seconds: None
    return c
