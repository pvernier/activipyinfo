import json
import sys
from datetime import date, datetime

import pytest

from activipyinfo import (
    DateField,
    FormSchema,
    MultilineField,
    QuantityField,
    SingleSelectField,
    TextField,
)
from activipyinfo._pandas import is_missing, require_pandas
from activipyinfo.models.values import encode_value

pd = pytest.importorskip("pandas")
np = pytest.importorskip("numpy")

API = "https://www.activityinfo.org/resources"


# ----------------------------------------------------------------------
# FormSchema.from_data
# ----------------------------------------------------------------------


@pytest.fixture
def frame():
    return pd.DataFrame(
        {
            "Head of household": ["Alice", "Bob", None],
            "Members": [5, 2, 3],
            "Income": [12.5, None, 3.0],
            "Displaced": [True, False, True],
            "Status": pd.Categorical(["A", "B", "A"], categories=["A", "B", "C"]),
            "Visit date": pd.to_datetime(["2024-03-01", "2024-03-02", None]),
            "Notes": ["short", "line 1\nline 2", None],
            "1st contact": ["x", "y", "z"],
        }
    )


def test_from_data_infers_field_types(frame):
    schema = FormSchema.from_data(frame, "Households", keys=["Head of household"])

    types = {f.label: type(f) for f in schema}
    assert types == {
        "Head of household": TextField,
        "Members": QuantityField,
        "Income": QuantityField,
        "Displaced": SingleSelectField,
        "Status": SingleSelectField,
        "Visit date": DateField,
        "Notes": MultilineField,
        "1st contact": TextField,
    }
    assert schema.label == "Households"
    assert schema["Head of household"].key is True
    assert schema["Head of household"].required is True
    assert [o.label for o in schema["Status"].options] == ["A", "B", "C"]
    assert [o.label for o in schema["Displaced"].options] == ["True", "False"]


def test_from_data_derives_codes(frame):
    schema = FormSchema.from_data(frame, "Households")

    assert [f.code for f in schema] == [
        "Head_of_household",
        "Members",
        "Income",
        "Displaced",
        "Status",
        "Visit_date",
        "Notes",
        "st_contact",
    ]


def test_from_data_without_codes(frame):
    schema = FormSchema.from_data(frame, "Households", codes=False)

    assert all(f.code is None for f in schema)


def test_codes_are_unique_and_valid():
    rows = [{"Name": "a", "name": "b", "Prénom": "c", "?!": "d", "x" * 40: "e"}]

    codes = [f.code for f in FormSchema.from_data(rows, "F")]

    assert codes == ["Name", "name_2", "Prenom", None, "x" * 32]


def test_from_list_of_dicts():
    rows = [
        {"name": "A", "age": 3, "born": date(2020, 1, 1)},
        {"name": "B", "when": datetime(2024, 1, 1, 12)},
    ]

    schema = FormSchema.from_data(rows, "People", required=["name"])

    assert [type(f) for f in schema] == [TextField, QuantityField, DateField, DateField]
    assert schema["name"].required is True
    assert schema["name"].key is False


def test_from_data_errors(frame):
    with pytest.raises(ValueError, match="Unknown columns"):
        FormSchema.from_data(frame, "F", keys=["Nope"])
    with pytest.raises(ValueError, match="cannot be a key"):
        FormSchema.from_data(frame, "F", keys=["Members"])


# ----------------------------------------------------------------------
# Values from pandas
# ----------------------------------------------------------------------


@pytest.mark.parametrize("value", [None, float("nan"), pd.NA, pd.NaT, np.nan])
def test_missing_values(value):
    assert is_missing(value)


@pytest.mark.parametrize("value", [0, "", "x", [1, 2], np.int64(3)])
def test_present_values(value):
    assert not is_missing(value)


def test_numpy_numbers_become_plain_numbers():
    field = QuantityField("Q")

    assert type(encode_value(field, np.int64(3))) is int
    assert type(encode_value(field, np.float64(2.5))) is float
    with pytest.raises(TypeError):
        encode_value(field, np.bool_(True))


def test_booleans_select_true_false_options():
    field = SingleSelectField("Displaced", ["True", "False"])

    assert encode_value(field, np.bool_(False)) == field.option("False").id
    assert encode_value(field, True) == field.option("True").id


def test_add_many_from_a_dataframe(client, mocked, tree_data, frame):
    mocked.get(f"{API}/databases/db1", json=tree_data)
    schema = FormSchema.from_data(frame, "Households", keys=["Head of household"])
    schema.id = "fma1"
    mocked.get(f"{API}/form/fma1/schema", json=schema.to_api())
    mocked.post(f"{API}/update", json={})
    form = client.databases.get("db1").form("fma1")

    ids = form.records.add_many(frame.head(2))

    changes = json.loads(mocked.calls[-1].request.body)["changes"]
    assert len(ids) == 2
    first, second = (change["fields"] for change in changes)
    by_label = {f.label: f.id for f in schema}
    assert first[by_label["Members"]] == 5
    assert first[by_label["Visit date"]] == "2024-03-01"
    assert first[by_label["Displaced"]] == schema["Displaced"].option("True").id
    assert first[by_label["Status"]] == schema["Status"].option("A").id
    assert second[by_label["Income"]] is None  # NaN clears the field


# ----------------------------------------------------------------------
# DataFrames of schemas and users
# ----------------------------------------------------------------------


def test_schema_to_pandas():
    schema = FormSchema("F", [TextField("Name", code="name")])

    frame = schema.to_pandas()

    assert frame.loc[0, "code"] == "name"
    assert list(frame.columns)[:4] == ["field_id", "code", "label", "type"]


def test_users_to_pandas(client, mocked, tree_data):
    mocked.get(f"{API}/databases/db1", json=tree_data)
    mocked.get(
        f"{API}/databases/db1/users",
        json=[
            {
                "userId": "1",
                "email": "a@example.org",
                "name": "A",
                "role": {"id": "readonly", "parameters": {}, "resources": ["db1"]},
            }
        ],
    )

    frame = client.databases.get("db1").users.to_pandas()

    assert frame.loc[0, "role_id"] == "readonly"
    assert frame.loc[0, "email"] == "a@example.org"


def test_missing_pandas_is_explained(monkeypatch):
    monkeypatch.setitem(sys.modules, "pandas", None)

    with pytest.raises(ImportError, match=r"activipyinfo\[pandas\]"):
        require_pandas()
