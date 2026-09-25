import copy
import json
from pathlib import Path

import pytest

from activipyinfo import Client


@pytest.fixture
def client() -> Client:
    """A client whose retries do not sleep."""
    c = Client("test-token", backoff_factor=0)
    c._sleep = lambda seconds: None
    return c


FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def tree_data():
    """A fresh copy of the sample database tree (safe to mutate)."""
    return copy.deepcopy(load_fixture("database_tree.json"))
