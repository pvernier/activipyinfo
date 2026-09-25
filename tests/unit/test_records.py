import json
from datetime import UTC, date, datetime

import pytest
import responses

from activipyinfo import (
    DateField,
    FormSchema,
    MultipleMatchesError,
    NoMatchError,
    QuantityField,
    QueryResult,
    Record,
    RecordBatchError,
    ReferenceField,
    SelectOption,
    SingleSelectField,
    TextField,
)
from activipyinfo.services.records import change

API = "https://www.activityinfo.org/resources"

SCHEMA = FormSchema(
    "Households",
    [
        TextField("Head of household", code="head", key=True, id="fhead"),
        QuantityField("Members", code="members", id="fmembers"),
        SingleSelectField(
            "Status",
            [SelectOption("Resident", id="res"), SelectOption("Displaced", id="dis")],
            code="status",
            id="fstatus",
        ),
        DateField("Visit date", code="visit", id="fvisit"),
        ReferenceField("Province", "cprov", code="province", id="fprov"),
    ],
    id="fma1",
    database_id="db1",
)

RECORD = {
    "recordId": "r1",
    "formId": "fma1",
    "lastEditTime": 1_700_000_000_000,
    "fields": {
        "fhead": "Alice",
        "fmembers": 5,
        "fstatus": "dis",
        "fvisit": "2024-03-01",
        "fprov": "cprov:p1",
    },
}


def sent_json(mocked, index=-1):
    return json.loads(mocked.calls[index].request.body)


def columns_response(**columns):
    n_rows = max(len(v) for v in columns.values()) if columns else 0
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
    """The Admin1 form (fma1) with the SCHEMA above, fetched once."""
    mocked.get(f"{API}/form/fma1/schema", json=SCHEMA.to_api())
    return db.form("fma1")


# ----------------------------------------------------------------------
# QueryResult and client.queries
# ----------------------------------------------------------------------


def test_query_result_storage_modes():
    data = {
        "rows": 3,
        "offset": 10,
        "totalRows": 50,
        "columns": {
            "id": {"type": "STRING", "storage": "array", "values": ["a", "b", None]},
            "n": {"type": "NUMBER", "storage": "constant", "value": 1},
            "x": {"type": "STRING", "storage": "empty"},
        },
    }

    result = QueryResult.from_api(data, ["x", "id", "n", "missing"])

    assert result.total_rows == 50
    assert result.offset == 10
    assert len(result) == 3
    assert result[0] == {"x": None, "id": "a", "n": 1, "missing": None}
    assert [row["id"] for row in result] == ["a", "b", None]


def test_query_result_rejects_inconsistent_columns():
    with pytest.raises(ValueError, match="2 values for 3 rows"):
        QueryResult.from_api(
            {"rows": 3, "columns": {"a": {"storage": "array", "values": [1, 2]}}}
        )


def test_query_all_columns_uses_get(client, mocked):
    mocked.get(
        f"{API}/form/fma1/query/columns",
        match=[responses.matchers.query_param_matcher({"_truncate": "false"})],
        json=columns_response(a=["1"]),
    )

    assert client.queries.columns("fma1").rows == [{"a": "1"}]


def test_query_payload_matches_r_package(client, mocked):
    mocked.post(f"{API}/query/columns", json=columns_response(id=["r1"], name=["A"]))

    result = client.queries.columns(
        "fma1",
        {"id": "_id", "name": "head"},
        filter="members > 2",
        sort=["head", ("visit", "desc")],
        offset=5,
        limit=10,
    )

    assert sent_json(mocked) == {
        "rowSources": [{"rootFormId": "fma1"}],
        "columns": [
            {"id": "id", "expression": "_id"},
            {"id": "name", "expression": "head"},
        ],
        "truncateStrings": False,
        "filter": "members > 2",
        "sort": [{"field": "head", "dir": "ASC"}, {"field": "visit", "dir": "DESC"}],
        "window": [5, 10],
    }
    assert result.rows == [{"id": "r1", "name": "A"}]


def test_query_with_list_of_formulas(client, mocked):
    mocked.post(f"{API}/query/columns", json=columns_response(head=["A"]))

    client.queries.columns("fma1", ["head"], limit=1)

    assert sent_json(mocked)["columns"] == [{"id": "head", "expression": "head"}]
    assert sent_json(mocked)["window"] == [0, 1]


def test_query_validation(client):
    with pytest.raises(ValueError, match="columns are required"):
        client.queries.columns("fma1", filter="x")
    with pytest.raises(ValueError, match="ASC or DESC"):
        client.queries.columns("fma1", ["x"], sort=[("x", "up")])


# ----------------------------------------------------------------------
# client.records
# ----------------------------------------------------------------------


def test_change_builder():
    assert change("f", "r", {"a": 1}) == {
        "formId": "f",
        "recordId": "r",
        "deleted": False,
        "fields": {"a": 1},
    }
    assert change("f", "r", parent_record_id="p")["parentRecordId"] == "p"
    assert change("f", "r", deleted=True) == {
        "formId": "f",
        "recordId": "r",
        "deleted": True,
        "fields": None,
    }


def test_get_and_exists(client, mocked):
    mocked.get(f"{API}/form/fma1/record/r1", json=RECORD)
    mocked.get(f"{API}/form/fma1/record/r1", json=RECORD)
    mocked.get(f"{API}/form/fma1/record/nope", status=404, json={"code": "NOT_FOUND"})

    record = client.records.get("fma1", "r1")

    assert record.record_id == "r1"
    assert record.fields["fmembers"] == 5
    assert record.last_edit_time == datetime.fromtimestamp(1_700_000_000, tz=UTC)
    assert client.records.exists("fma1", "r1") is True
    assert client.records.exists("fma1", "nope") is False


def test_submit_in_batches(client, mocked):
    mocked.post(f"{API}/update", json={})

    ids = client.records.submit((change("f", f"r{i}") for i in range(5)), batch_size=2)

    assert ids == ["r0", "r1", "r2", "r3", "r4"]
    assert [len(sent_json(mocked, i)["changes"]) for i in range(3)] == [2, 2, 1]


def test_submit_reports_what_was_applied(client, mocked):
    mocked.post(f"{API}/update", json={})
    mocked.post(f"{API}/update", status=400, json={"code": "INVALID", "message": "Bad"})

    with pytest.raises(RecordBatchError) as info:
        client.records.submit([change("f", f"r{i}") for i in range(4)], batch_size=2)

    assert info.value.submitted == ["r0", "r1"]
    assert [c["recordId"] for c in info.value.failed] == ["r2", "r3"]
    assert "Bad" in str(info.value)


def test_submit_rejects_bad_batch_size(client):
    with pytest.raises(ValueError, match="batch_size"):
        client.records.submit([], batch_size=201)


def test_history_and_recover(client, mocked):
    mocked.get(
        f"{API}/form/fma1/record/r1/history",
        json={
            "entries": [
                {
                    "formId": "fma1",
                    "recordId": "r1",
                    "version": 2,
                    "time": 1_700_000_000,
                    "changeType": "UPDATE",
                    "user": {"name": "Alice", "email": "a@example.org"},
                    "values": [{"fieldId": "fmembers", "value": 5}],
                }
            ]
        },
    )
    mocked.post(f"{API}/form/fma1/record/r1/recover", json={})

    (entry,) = client.records.history("fma1", "r1")
    client.records.recover("fma1", "r1")

    assert entry.change_type == "UPDATE"
    assert entry.user_email == "a@example.org"
    assert entry.time == datetime.fromtimestamp(1_700_000_000, tz=UTC)


# ----------------------------------------------------------------------
# Record
# ----------------------------------------------------------------------


def test_record_values_by_code_id_or_label():
    record = Record.from_api(RECORD, SCHEMA)

    assert record["head"] == "Alice"
    assert record["fmembers"] == 5
    assert record["Status"] == "Displaced"
    assert record["visit"] == date(2024, 3, 1)
    assert record["province"] == "p1"
    assert record.get("missing", "?") == "?"


def test_record_to_dict():
    record = Record.from_api(RECORD, SCHEMA)

    assert record.to_dict() == {
        "head": "Alice",
        "members": 5,
        "status": "Displaced",
        "visit": date(2024, 3, 1),
        "province": "p1",
    }
    assert list(record.to_dict("label"))[0] == "Head of household"
    assert list(record.to_dict("id"))[0] == "fhead"
    with pytest.raises(ValueError):
        record.to_dict("name")


def test_record_without_schema():
    record = Record.from_api(RECORD)

    assert record["fhead"] == "Alice"
    with pytest.raises(ValueError, match="no schema"):
        record.to_dict()


def test_records_compare_by_form_and_id():
    assert Record("r1", "f") == Record("r1", "f", fields={"a": 1})
    assert Record("r1", "f") != Record("r1", "g")


# ----------------------------------------------------------------------
# form.records
# ----------------------------------------------------------------------


def test_add_converts_values_and_returns_the_saved_record(form, mocked):
    mocked.post(f"{API}/update", json={})
    mocked.add_callback(
        responses.GET,
        responses.matchers.re.compile(rf"{API}/form/fma1/record/\w+"),
        callback=lambda request: (
            200,
            {},
            json.dumps({**RECORD, "recordId": request.url.rsplit("/", 1)[1]}),
        ),
    )

    record = form.records.add(
        {"head": "Alice", "Status": "Displaced", "visit": date(2024, 3, 1)},
        province=Record("p1", "cprov"),
        members=5,
    )

    (entry,) = sent_json(mocked, 1)["changes"]
    assert entry["formId"] == "fma1"
    assert entry["recordId"] == record.record_id
    assert entry["deleted"] is False
    assert "parentRecordId" not in entry
    assert entry["fields"] == {
        "fhead": "Alice",
        "fstatus": "dis",
        "fvisit": "2024-03-01",
        "fprov": "p1",
        "fmembers": 5,
    }
    assert record.schema is not None
    assert record["status"] == "Displaced"


def test_schema_is_fetched_once(form, mocked):
    mocked.post(f"{API}/update", json={})

    form.records.add_many([{"head": "A"}, {"head": "B"}])
    form.records.update_many([{"_id": "r1", "members": 3}])

    schema_calls = [c for c in mocked.calls if c.request.url.endswith("/schema")]
    assert len(schema_calls) == 1


def test_unknown_field_is_rejected_before_sending(form, mocked):
    with pytest.raises(KeyError, match="no field 'age'"):
        form.records.add({"age": 3}, record_id="r9")

    assert not [c for c in mocked.calls if c.request.url.endswith("/update")]


def test_add_with_explicit_id_and_parent(form, mocked):
    mocked.post(f"{API}/update", json={})
    mocked.get(f"{API}/form/fma1/record/r9", json={**RECORD, "recordId": "r9"})

    form.records.add({"head": "A"}, record_id="r9", parent=Record("p1", "cparent"))

    (entry,) = sent_json(mocked, 1)["changes"]
    assert entry["recordId"] == "r9"
    assert entry["parentRecordId"] == "p1"


def test_subform_records_need_a_parent(db):
    # Checked before anything is sent or even the schema is fetched.
    with pytest.raises(ValueError, match="subform"):
        db.form("sfhh").records.add_many([{}])


def test_add_many(form, mocked):
    mocked.post(f"{API}/update", json={})

    ids = form.records.add_many(
        [
            {"_id": "r1", "head": "A", "members": 1},
            {"head": "B", "_parent": "p2"},
            {"head": "C"},
        ],
        parent="p1",
        batch_size=2,
    )

    first, second = sent_json(mocked, 1)["changes"]
    (third,) = sent_json(mocked, 2)["changes"]
    assert ids[0] == "r1"
    assert len(ids) == 3
    assert first == {
        "formId": "fma1",
        "recordId": "r1",
        "parentRecordId": "p1",
        "deleted": False,
        "fields": {"fhead": "A", "fmembers": 1},
    }
    assert second["parentRecordId"] == "p2"
    assert third["parentRecordId"] == "p1"


def test_update_does_not_touch_the_parent(form, mocked):
    mocked.post(f"{API}/update", json={})
    mocked.get(f"{API}/form/fma1/record/r1", json=RECORD)

    record = form.records.update("r1", {"members": None}, head="Bob")

    (entry,) = sent_json(mocked, 1)["changes"]
    assert entry == {
        "formId": "fma1",
        "recordId": "r1",
        "deleted": False,
        "fields": {"fmembers": None, "fhead": "Bob"},
    }
    assert record.record_id == "r1"


def test_update_many_requires_ids(db):
    with pytest.raises(ValueError, match="_id"):
        db.form("fma1").records.update_many([{"head": "A"}])


def test_delete_and_recover(form, mocked):
    mocked.post(f"{API}/update", json={})
    mocked.post(f"{API}/form/fma1/record/r1/recover", json={})
    mocked.get(f"{API}/form/fma1/record/r1", json=RECORD)

    form.records.delete(Record("r1", "fma1"))
    form.records.delete_many(["r2", "r3"])
    restored = form.records.recover("r1")

    assert sent_json(mocked, 0)["changes"] == [change("fma1", "r1", deleted=True)]
    assert [c["recordId"] for c in sent_json(mocked, 1)["changes"]] == ["r2", "r3"]
    assert restored.record_id == "r1"


def test_find_all_builds_a_filter(form, mocked):
    mocked.post(f"{API}/query/columns", json=columns_response(_id=["r1", "r2"]))

    ids = form.records.find_all(
        head='Al "the" \\ Great', members=5, status="dis", visit=date(2024, 3, 1)
    )

    query = sent_json(mocked)
    assert query["columns"] == [{"id": "_id", "expression": "_id"}]
    assert query["filter"] == (
        'head == "Al \\"the\\" \\\\ Great" && members == 5 && '
        'status == "Displaced" && visit == "2024-03-01"'
    )
    assert ids == ["r1", "r2"]


def test_ref_and_find(form, mocked):
    mocked.post(f"{API}/query/columns", json=columns_response(_id=["r1"]))
    mocked.post(f"{API}/query/columns", json=columns_response(_id=["r1"]))
    mocked.get(f"{API}/form/fma1/record/r1", json=RECORD)

    assert form.records.ref(head="Alice") == "r1"
    assert form.records.find(head="Alice")["members"] == 5


def test_ref_without_or_with_several_matches(form, mocked):
    mocked.post(f"{API}/query/columns", json=columns_response(_id=[]))
    mocked.post(f"{API}/query/columns", json=columns_response(_id=["r1", "r2"]))

    with pytest.raises(NoMatchError, match="head='Nobody'"):
        form.records.ref(head="Nobody")
    with pytest.raises(MultipleMatchesError):
        form.records.ref(head="Twin")


def test_find_all_needs_criteria(db):
    with pytest.raises(ValueError, match="at least one"):
        db.form("fma1").records.find_all()


def test_list(form, mocked):
    mocked.post(
        f"{API}/query/columns",
        json=columns_response(
            _id=["r1", "r2"],
            fhead=["Alice", "Bob"],
            fmembers=[5, None],
            fstatus=["Displaced", None],
            fvisit=["2024-03-01", None],
            fprov=["p1", None],
        ),
    )

    records = form.records.list(filter="members > 1", limit=10)

    query = sent_json(mocked)
    assert query["columns"][0] == {"id": "_id", "expression": "_id"}
    assert query["filter"] == "members > 1"
    assert query["window"] == [0, 10]
    assert [r.record_id for r in records] == ["r1", "r2"]
    assert records[0]["status"] == "Displaced"
    assert records[0]["visit"] == date(2024, 3, 1)
    assert records[1].to_dict() == {"head": "Bob"}


def test_form_records_accessor_is_cached(db):
    form = db.form("fma1")

    assert form.records is form.records
