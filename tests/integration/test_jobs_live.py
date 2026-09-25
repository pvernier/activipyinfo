"""Live checks of jobs: imports, exports, XLSForms, audit log and duplication.

They run in a scratch folder (see conftest.py).
"""

import csv

import pytest

from activipyinfo import (
    BadRequestError,
    JobFailedError,
    PermissionDeniedError,
    QuantityField,
    SingleSelectField,
    TextField,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def people(sandbox):
    return sandbox.folder.add_form(
        "People",
        [
            TextField("Code", code="code", key=True),
            QuantityField("Age", code="age"),
            SingleSelectField("Status", ["Active", "Closed"], code="status"),
        ],
    )


def test_bulk_import_adds_then_updates_by_key(people):
    rows = [{"code": f"P{i:03d}", "age": i, "status": "Active"} for i in range(50)]

    job = people.records.bulk_import(rows)
    assert job.completed
    assert people.table().count() == 50

    # Same keys: the existing records are updated, not duplicated.
    people.records.bulk_import([{"code": "P001", "age": 99, "status": "Closed"}])
    assert people.table().count() == 50
    (row,) = people.table().select("age", "status").where(code="P001").collect()
    assert (row["age"], row["status"]) == (99, "Closed")


def test_form_export(people, tmp_path):
    people.records.add_many([{"code": "A", "age": 1}, {"code": "B", "age": 2}])

    path = people.table().select("code", "age").sort("code").export("csv", tmp_path)

    with path.open(encoding="utf-8-sig") as file:
        rows = list(csv.reader(file))
    assert path.exists()
    assert rows[0][-2:] == ["code", "age"]
    assert [r[-2] for r in rows[1:]] == ["A", "B"]


def test_database_export_of_a_folder(sandbox, people, tmp_path):
    people.records.add(code="A", age=1)

    path = sandbox.db.export("xlsx", tmp_path, folder=sandbox.folder)

    assert path.exists() and path.stat().st_size > 0


def test_import_xlsform(sandbox, tmp_path):
    pd = pytest.importorskip("pandas")
    pytest.importorskip("openpyxl")
    xlsform = tmp_path / "survey.xlsx"
    with pd.ExcelWriter(xlsform) as writer:
        pd.DataFrame(
            {
                "type": ["text", "integer"],
                "name": ["name", "age"],
                "label": ["Name", "Age"],
            }
        ).to_excel(writer, sheet_name="survey", index=False)
        pd.DataFrame({"form_title": ["Survey"], "form_id": ["survey"]}).to_excel(
            writer, sheet_name="settings", index=False
        )

    form = sandbox.db.import_xlsform(xlsform, parent=sandbox.folder)

    assert form.parent.id == sandbox.folder.id
    assert {"name", "age"} <= {f.code for f in form.schema()}


def test_audit_log(sandbox, people):
    try:
        events = sandbox.db.audit_log(limit=20)
    except PermissionDeniedError:
        pytest.skip("the token's user cannot read the audit log of this database")

    assert events
    assert all(e.time is not None for e in events)


def test_duplicate_database(live_client, sandbox):
    try:
        copy = sandbox.db.duplicate("activipyinfo test copy (safe to delete)")
    except (BadRequestError, PermissionDeniedError, JobFailedError) as exc:
        pytest.skip(f"this account cannot duplicate databases: {exc}")
    try:
        assert copy.id != sandbox.db.id
        assert copy.label == "activipyinfo test copy (safe to delete)"
    finally:
        copy.delete()
