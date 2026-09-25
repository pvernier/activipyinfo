"""Live checks of tables and DataFrames, in a scratch folder (see conftest.py)."""

from datetime import date

import pytest

from activipyinfo import (
    DateField,
    FormSchema,
    QuantityField,
    ReferenceField,
    SingleSelectField,
    TextField,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def forms(sandbox):
    folder = sandbox.folder
    provinces = folder.add_form(
        "Provinces",
        [
            TextField("P-code", code="pcode", key=True),
            TextField("Name", code="name"),
        ],
    )
    households = folder.add_form(
        FormSchema(
            "Households",
            [
                TextField("Head", code="head", key=True),
                ReferenceField("Province", provinces, code="province"),
                QuantityField("Members", code="members"),
                SingleSelectField("Status", ["Resident", "Displaced"], code="status"),
                DateField("Visit date", code="visit"),
            ],
        )
    )
    provinces.records.add_many(
        [
            {"pcode": "LBN001", "name": "Mount Lebanon"},
            {"pcode": "LBN002", "name": "Bekaa"},
        ]
    )
    bekaa = provinces.records.ref(pcode="LBN002")
    households.records.add_many(
        [
            {
                "head": "Alice",
                "province": bekaa,
                "members": 5,
                "status": "Displaced",
                "visit": date(2024, 3, 1),
            },
            {"head": "Bob", "province": bekaa, "members": 2, "status": "Resident"},
            {"head": "Carla", "members": 7, "status": "Displaced"},
        ]
    )
    return provinces, households


def test_default_columns_follow_references(forms):
    _, households = forms

    rows = {row["Head"]: row for row in households.table().collect()}

    assert rows["Alice"]["Province P-code"] == "LBN002"
    assert rows["Alice"]["Status"] == "Displaced"
    assert rows["Alice"]["Visit date"] == date(2024, 3, 1)
    assert rows["Carla"]["Province P-code"] is None


def test_query_building(forms):
    _, households = forms
    table = (
        households.table()
        .select("head", "members", province="province.name")
        .where(status="Displaced")
        .sort("members", desc=True)
    )

    assert [(r["head"], r["province"]) for r in table.collect()] == [
        ("Carla", None),
        ("Alice", "Bekaa"),
    ]
    assert table.count() == 2
    assert table.offset(1).limit(1).collect()[0]["head"] == "Alice"
    assert households.table().filter("members > 4").count() == 2


def test_to_pandas(forms):
    pytest.importorskip("pandas")
    _, households = forms

    frame = households.to_pandas(names="code")

    assert set(frame["head"]) == {"Alice", "Bob", "Carla"}
    assert "province.pcode" in frame.columns
    assert str(frame["visit"].dtype).startswith("datetime64")


def test_subform_table_has_parent(sandbox):
    visits = sandbox.folder.add_form("Visits", [TextField("Village", code="village")])
    members = visits.add_subform("Members", [TextField("Name", code="name")])
    visit = visits.records.add(village="Zahle")
    members.records.add({"name": "Rami"}, parent=visit)

    (row,) = members.table().collect()

    assert row["_parent"] == visit.record_id
    assert row["Name"] == "Rami"


def test_dataframe_round_trip(sandbox):
    pd = pytest.importorskip("pandas")
    frame = pd.DataFrame(
        {
            "Name": ["A", "B"],
            "Age": [3, None],
            "Registered": [True, False],
            "Born": pd.to_datetime(["2020-01-01", "2021-06-30"]),
        }
    )
    form = sandbox.folder.add_form(FormSchema.from_data(frame, "People", keys=["Name"]))

    form.records.add_many(frame)
    back = form.to_pandas().sort_values("Name").reset_index(drop=True)

    assert back["Name"].tolist() == ["A", "B"]
    assert back["Age"].tolist()[0] == 3
    assert pd.isna(back["Age"].tolist()[1])
    assert back["Registered"].tolist() == ["True", "False"]
    assert back["Born"].tolist() == list(frame["Born"])
