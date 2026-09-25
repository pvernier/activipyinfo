import string

import pytest

from activipyinfo.ids import cuid, is_cuid

ALPHANUMERIC = string.ascii_lowercase + string.digits


def test_cuid_shape():
    unique_id = cuid()

    assert len(unique_id) == 24
    assert unique_id[0] in string.ascii_lowercase
    assert all(c in ALPHANUMERIC for c in unique_id[1:])


def test_cuid_custom_length():
    assert len(cuid(10)) == 10


@pytest.mark.parametrize("length", [1, 33])
def test_cuid_rejects_invalid_length(length):
    with pytest.raises(ValueError):
        cuid(length)


def test_cuids_are_unique():
    ids = {cuid() for _ in range(10_000)}

    assert len(ids) == 10_000


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("ck8oykh8m5", True),
        (cuid(), True),
        ("1abc", False),
        ("Abc", False),
        ("ab-c", False),
        ("a", False),
        (None, False),
    ],
)
def test_is_cuid(value, expected):
    assert is_cuid(value) is expected
