import json
from dataclasses import FrozenInstanceError
from datetime import date

import pytest

from activipyinfo import (
    DateField,
    FormSchema,
    QuantityField,
    ReferenceField,
    SectionHeader,
    SelectOption,
    SingleSelectField,
    SubformField,
    Table,
    TextField,
)
from activipyinfo.models.table import default_columns

API = "https://www.activityinfo.org/resources"

PROVINCES = FormSchema(
    "Provinces",
    [
        TextField("P-code", code="pcode", key=True, id="fpcode"),
        TextField("Name", code="name", id="fname"),
    ],
    id="cprov",
)
HOUSEHOLDS = FormSchema(
    "Households",
    [
        SectionHeader("About", id="fsec"),
        TextField("Head", code="head", key=True, id="fhead"),
        ReferenceField("Province", "cprov", code="province", id="fprov"),
        QuantityField("Members", code="members", id="fmembers"),
        SingleSelectField(
            "Status",
            [SelectOption("Resident", id="res"), SelectOption("Displaced", id="dis")],
            code="status",
            id="fstatus",
        ),
        DateField("Visit date", code="visit", id="fvisit"),
        SubformField("Members list", "csub", id="fsub"),
    ],
    id="fma1",
    database_id="db1",
)


def sent_json(mocked, index=-1):
    return json.loads(mocked.calls[index].request.body)


def columns_response(**columns):
    n_rows = max((len(v) for v in columns.values()), default=0)
    return {
        "rows": n_rows,
        "offset": 0,
        "totalRows": n_rows,
        "columns": {
            name: {"type": "STRING", "storage": "array", "values": values}
            for name, values in columns.items()
        },
    }


@pytest.fixture
def db(client, mocked, tree_data):
    mocked.get(f"{API}/databases/db1", json=tree_data)
    database = client.databases.get("db1")
    mocked.calls.reset()
    return database


@pytest.fixture
def form(db, mocked):
    mocked.get(f"{API}/form/fma1/schema", json=HOUSEHOLDS.to_api())
    return db.form("fma1")


@pytest.fixture
def tree(mocked):
    mocked.get(
        f"{API}/form/fma1/tree",
        json={
            "root": "fma1",
            "forms": {
                "fma1": {"schema": HOUSEHOLDS.to_api()},
                "cprov": {"schema": PROVINCES.to_api()},
            },
        },
    )


# ----------------------------------------------------------------------
# Default columns
# ----------------------------------------------------------------------


def test_default_columns_expand_references_to_key_fields():
    columns = default_columns(HOUSEHOLDS, {"cprov": PROVINCES})

    assert {name: formula for name, (formula, _) in columns.items()} == {
        "_id": "_id",
        "Head": "fhead",
        "Province P-code": "fprov.fpcode",
        "Members": "fmembers",
        "Status": "fstatus",
        "Visit date": "fvisit",
    }
    assert columns["Province P-code"][1].code == "pcode"


@pytest.mark.parametrize(
    ("names", "expected"),
    [
        ("code", ["_id", "head", "province.pcode", "members", "status", "visit"]),
        ("id", ["_id", "fhead", "fprov.fpcode", "fmembers", "fstatus", "fvisit"]),
    ],
)
def test_default_column_names(names, expected):
    assert list(default_columns(HOUSEHOLDS, {"cprov": PROVINCES}, names=names)) == (
        expected
    )


def test_unknown_referenced_form_keeps_the_record_id():
    columns = default_columns(HOUSEHOLDS)

    assert columns["Province"][0] == "fprov"


def test_subform_tables_have_a_parent_column():
    subform = FormSchema("Members", [TextField("Name")], parent_form_id="fma1")

    assert list(default_columns(subform))[:2] == ["_id", "_parent"]
    assert default_columns(subform)["_parent"][0] == "@parent"


def test_duplicate_column_names_are_made_unique():
    schema = FormSchema("F", [TextField("Name"), TextField("Name")])

    assert list(default_columns(schema)) == ["_id", "Name", "Name (2)"]


def test_form_tree_endpoint(client, mocked, tree):
    forms = client.forms.tree("fma1")

    assert set(forms) == {"fma1", "cprov"}
    assert forms["cprov"].key_fields[0].code == "pcode"


def test_form_tree_as_a_list(client, mocked):
    mocked.get(
        f"{API}/form/fma1/tree",
        json={"forms": [{"schema": PROVINCES.to_api()}]},
    )

    assert list(client.forms.tree("fma1")) == ["cprov"]


# ----------------------------------------------------------------------
# Building queries
# ----------------------------------------------------------------------


def test_table_is_immutable(db):
    table = db.form("fma1").table()

    assert table.limit(5) is not table
    assert table.max_rows is None
    with pytest.raises(FrozenInstanceError):
        table.max_rows = 3


def test_default_query(form, mocked, tree):
    mocked.post(
        f"{API}/query/columns",
        json=columns_response(
            **{
                "_id": ["r1", "r2"],
                "Head": ["Alice", "Bob"],
                "Province P-code": ["LBN001", None],
                "Members": [5, 2],
                "Status": ["Displaced", "Resident"],
                "Visit date": ["2024-03-01", None],
            }
        ),
    )

    rows = form.table().collect()

    query = sent_json(mocked)
    assert query["rowSources"] == [{"rootFormId": "fma1"}]
    assert query["columns"][2] == {
        "id": "Province P-code",
        "expression": "fprov.fpcode",
    }
    assert "filter" not in query and "window" not in query
    assert rows[0] == {
        "_id": "r1",
        "Head": "Alice",
        "Province P-code": "LBN001",
        "Members": 5,
        "Status": "Displaced",
        "Visit date": date(2024, 3, 1),
    }


def test_select_where_filter_sort_offset_limit(form, mocked, tree):
    mocked.post(f"{API}/query/columns", json=columns_response(_id=[], head=[]))

    table = (
        form.table()
        .select("head", "Members", "status", province_name="province.name")
        .where(status="Displaced")
        .filter("members > 2")
        .sort("members", desc=True)
        .sort("head")
        .offset(10)
        .limit(5)
    )
    table.collect()

    query = sent_json(mocked)
    assert query["columns"] == [
        {"id": "_id", "expression": "_id"},
        {"id": "head", "expression": "fhead"},
        {"id": "Members", "expression": "fmembers"},
        {"id": "status", "expression": "fstatus"},
        {"id": "province_name", "expression": "province.name"},
    ]
    assert query["filter"] == 'status == "Displaced" && (members > 2)'
    assert query["sort"] == [
        {"field": "fmembers", "dir": "DESC"},
        {"field": "fhead", "dir": "ASC"},
    ]
    assert query["window"] == [10, 5]
    assert "Table(" in repr(table) and "limit=5" in repr(table)


def test_select_without_id(form):
    assert form.table().select("head", with_id=False).columns() == {"head": "fhead"}


def test_selected_values_are_decoded(form, mocked, tree):
    mocked.post(
        f"{API}/query/columns",
        json=columns_response(
            _id=["r1"], visit=["2024-03-01"], province=["cprov:p1"], code=["LBN001"]
        ),
    )

    (row,) = form.table().select("visit", "province", code="province.pcode").collect()

    assert row == {
        "_id": "r1",
        "visit": date(2024, 3, 1),
        "province": "p1",
        "code": "LBN001",
    }


def test_schema_is_fetched_once_per_chain(form, mocked):
    mocked.post(f"{API}/query/columns", json=columns_response(_id=[]))

    form.table().select("head").where(head="A").sort("members").collect()

    assert [c.request.url for c in mocked.calls].count(f"{API}/form/fma1/schema") == 1


def test_invalid_window(db):
    table = db.form("fma1").table()

    with pytest.raises(ValueError):
        table.offset(-1)
    with pytest.raises(ValueError):
        table.limit(-1)


# ----------------------------------------------------------------------
# Running queries
# ----------------------------------------------------------------------


def test_first_count_and_iteration(form, mocked):
    mocked.post(f"{API}/query/columns", json=columns_response(_id=["r1"], head=["A"]))
    mocked.post(f"{API}/query/columns", json=columns_response(_id=[]))
    mocked.post(f"{API}/query/columns", json=columns_response(_id=["r1", "r2", "r3"]))
    mocked.post(f"{API}/query/columns", json=columns_response(_id=["r1"], head=["A"]))

    table = form.table().select("head").filter("members > 1")

    assert table.first() == {"_id": "r1", "head": "A"}
    assert sent_json(mocked, 1)["window"] == [0, 1]
    assert table.first() is None
    assert table.limit(1).count() == 3
    count_query = sent_json(mocked, 3)
    assert count_query["columns"] == [{"id": "_id", "expression": "_id"}]
    assert count_query["filter"] == "(members > 1)"
    assert "window" not in count_query
    assert [row["head"] for row in table] == ["A"]


def test_to_pandas(form, mocked):
    pd = pytest.importorskip("pandas")
    mocked.post(
        f"{API}/query/columns",
        json=columns_response(
            _id=["r1", "r2"], visit=["2024-03-01", None], members=[5, 2]
        ),
    )

    frame = form.table().select("visit", "members").to_pandas()

    assert list(frame.columns) == ["_id", "visit", "members"]
    assert str(frame["visit"].dtype).startswith("datetime64")
    assert frame["visit"][0] == pd.Timestamp("2024-03-01")
    assert pd.isna(frame["visit"][1])
    assert frame["members"].tolist() == [5, 2]


def test_to_pandas_with_no_rows_keeps_columns(form, mocked):
    pytest.importorskip("pandas")
    mocked.post(f"{API}/query/columns", json=columns_response(_id=[], head=[]))

    frame = form.table().select("head").to_pandas()

    assert list(frame.columns) == ["_id", "head"]
    assert len(frame) == 0


def test_form_to_pandas_shortcut(form, mocked, tree):
    pytest.importorskip("pandas")
    mocked.post(f"{API}/query/columns", json=columns_response(_id=["r1"]))

    frame = form.to_pandas(names="code")

    assert "province.pcode" in frame.columns


def test_table_class_is_exported():
    assert Table.__name__ == "Table"
