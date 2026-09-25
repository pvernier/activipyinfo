"""Live checks of records. They run in a scratch folder (see conftest.py)."""

from datetime import date

import pytest

from activipyinfo import (
    DateField,
    FormSchema,
    GeoPointField,
    MultiSelectField,
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
                TextField("Head of household", code="head", key=True),
                ReferenceField("Province", provinces, code="province"),
                QuantityField("Members", code="members"),
                SingleSelectField("Status", ["Resident", "Displaced"], code="status"),
                MultiSelectField("Needs", ["Food", "Water", "Shelter"], code="needs"),
                DateField("Visit date", code="visit"),
                GeoPointField("Location", code="location"),
            ],
        )
    )
    return provinces, households


def test_record_lifecycle(forms):
    provinces, households = forms

    ids = provinces.records.add_many(
        [
            {"pcode": "LBN001", "name": "Mount Lebanon"},
            {"pcode": "LBN002", "name": "Bekaa"},
        ]
    )
    assert len(ids) == 2
    bekaa = provinces.records.ref(pcode="LBN002")
    assert bekaa in ids

    record = households.records.add(
        head="Alice",
        province=bekaa,
        members=5,
        status="Displaced",
        needs=["Food", "Water"],
        visit=date(2024, 3, 1),
        location=(33.85, 35.86),
    )

    # What the server kept, converted back to Python values.
    assert record["head"] == "Alice"
    assert record["province"] == bekaa
    assert record["members"] == 5
    assert record["status"] == "Displaced"
    assert sorted(record["needs"]) == ["Food", "Water"]
    assert record["visit"] == date(2024, 3, 1)
    assert record["location"]["latitude"] == pytest.approx(33.85)

    updated = households.records.update(record, members=6, visit=None)
    assert updated["members"] == 6
    assert updated.get("visit") is None

    assert households.records.find_all(status="Displaced") == [record.record_id]
    assert [r.record_id for r in households.records.list(filter="members > 5")] == [
        record.record_id
    ]
    assert households.records.find(head="Alice") == record

    assert len(households.records.history(record)) >= 2

    households.records.delete(record)
    assert not households.records.exists(record)
    households.records.recover(record)
    assert households.records.exists(record)


def test_subform_records(sandbox):
    visits = sandbox.folder.add_form("Visits", [TextField("Village", code="village")])
    members = visits.add_subform(
        "Members", [TextField("Name", code="name"), QuantityField("Age", code="age")]
    )
    visit = visits.records.add(village="Zahle")

    child = members.records.add({"name": "Rami", "age": 7}, parent=visit)

    assert child.parent_record_id == visit.record_id
    assert child["age"] == 7


def test_bulk_add_uses_several_batches(sandbox):
    bulk = sandbox.folder.add_form("Bulk", [QuantityField("N", code="n")])

    ids = bulk.records.add_many({"n": i} for i in range(205))

    assert len(ids) == len(set(ids)) == 205
    assert len(bulk.records.list()) == 205
