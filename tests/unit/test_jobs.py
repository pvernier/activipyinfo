import json
from datetime import UTC, datetime

import pytest

from activipyinfo import (
    APIError,
    DateField,
    FormSchema,
    GeoPointField,
    Job,
    JobFailedError,
    JobTimeoutError,
    MultiSelectField,
    QuantityField,
    SelectOption,
    SingleSelectField,
    TextField,
)

API = "https://www.activityinfo.org/resources"

EXPORT_RESULT = {
    "filename": "Households.csv",
    "downloadUrl": "/resources/jobs/j1/e1/Households.csv",
    "exportId": "e1",
}


def sent_json(mocked, index=-1):
    return json.loads(mocked.calls[index].request.body)


def job_status(state, **extra):
    return {"id": "j1", "state": state, "percentComplete": 50, **extra}


def columns_response(**columns):
    n_rows = max((len(v) for v in columns.values()), default=0)
    return {
        "rows": n_rows,
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


# ----------------------------------------------------------------------
# Jobs
# ----------------------------------------------------------------------


def test_job_parsing():
    job = Job.from_api(
        {
            "id": "j1",
            "state": "completed",
            "percentComplete": 100,
            "descriptor": {"type": "exportForm"},
            "jobResult": {"filename": "a.csv"},
        }
    )

    assert job.state == "COMPLETED"
    assert job.completed and not job.failed
    assert job.type == "exportForm"
    assert job.result == {"filename": "a.csv"}
    assert Job.from_api({"id": "j", "result": {"x": 1}}).result == {"x": 1}


def test_start_payload_matches_r_package(client, mocked):
    mocked.post(f"{API}/jobs", json=job_status("STARTED"))

    job = client.jobs.start("exportForm", {"a": 1})

    assert sent_json(mocked) == {
        "type": "exportForm",
        "locale": "en",
        "descriptor": {"a": 1},
    }
    assert job.type == "exportForm"
    assert job.state == "STARTED"


def test_run_polls_until_completed(client, mocked):
    mocked.post(f"{API}/jobs", json=job_status("STARTED"))
    mocked.get(f"{API}/jobs/j1", json=job_status("STARTED"))
    mocked.get(f"{API}/jobs/j1", json=job_status("COMPLETED", jobResult={"x": 1}))
    seen = []

    job = client.jobs.run("t", {}, progress=lambda j: seen.append(j.state))

    assert job.completed
    assert job.result == {"x": 1}
    assert seen == ["STARTED", "STARTED", "COMPLETED"]


def test_failed_job_raises(client, mocked):
    mocked.post(f"{API}/jobs", json=job_status("STARTED"))
    mocked.get(
        f"{API}/jobs/j1",
        json=job_status("FAILED", error={"code": "BAD_FILE", "message": "Oops"}),
    )

    with pytest.raises(JobFailedError, match="BAD_FILE Oops") as info:
        client.jobs.run("importRecords", {})

    assert info.value.job.error_code == "BAD_FILE"


def test_unknown_state_is_a_failure(client, mocked):
    mocked.post(f"{API}/jobs", json=job_status("CANCELLED"))

    with pytest.raises(JobFailedError):
        client.jobs.run("t", {})


def test_timeout(client, mocked):
    mocked.post(f"{API}/jobs", json=job_status("STARTED"))

    with pytest.raises(JobTimeoutError, match="50% done"):
        client.jobs.run("t", {}, timeout=0)


@pytest.mark.parametrize(
    "result",
    [
        EXPORT_RESULT,
        {**EXPORT_RESULT, "downloadUrl": f"{API}/jobs/j1/e1/Households.csv"},
        {k: v for k, v in EXPORT_RESULT.items() if k != "downloadUrl"},
    ],
)
def test_download(client, mocked, tmp_path, result):
    mocked.get(f"{API}/jobs/j1/e1/Households.csv", body=b"a,b\n1,2\n")
    job = Job.from_api({"id": "j1", "state": "COMPLETED", "jobResult": result}, client)

    path = job.download(tmp_path)

    assert path == tmp_path / "Households.csv"
    assert path.read_bytes() == b"a,b\n1,2\n"
    assert mocked.calls[0].request.headers["Authorization"] == "Bearer test-token"


def test_download_to_a_file_path(client, mocked, tmp_path):
    mocked.get(f"{API}/jobs/j1/e1/Households.csv", body=b"x")
    job = Job.from_api(
        {"id": "j1", "state": "COMPLETED", "jobResult": EXPORT_RESULT}, client
    )

    path = job.download(tmp_path / "out.csv")

    assert path.name == "out.csv"
    assert path.read_bytes() == b"x"


def test_download_needs_a_completed_job_with_a_file(client):
    with pytest.raises(ValueError, match="has not completed"):
        Job.from_api({"id": "j1", "state": "STARTED"}, client).download()
    with pytest.raises(ValueError, match="did not produce a file"):
        Job.from_api({"id": "j1", "state": "COMPLETED"}, client).download()


# ----------------------------------------------------------------------
# Staging
# ----------------------------------------------------------------------


def test_stage_through_activityinfo(client, mocked):
    mocked.post(
        f"{API}/imports/stage",
        json={"importId": "imp1", "uploadUrl": "/resources/imports/imp1"},
    )
    mocked.put(f"{API}/imports/imp1")

    assert client.jobs.stage("line 1\nline 2", content_type="text/plain") == "imp1"

    upload = mocked.calls[1].request
    assert upload.body == b"line 1\nline 2"
    assert upload.headers["Content-Type"] == "text/plain"
    assert upload.headers["Authorization"] == "Bearer test-token"


def test_stage_direct_to_signed_url_without_token(client, mocked):
    signed = "https://storage.googleapis.com/bucket/imp1?X-Goog-Signature=abc"
    mocked.post(
        f"{API}/imports/stage/direct", json={"importId": "imp1", "uploadUrl": signed}
    )
    mocked.put(signed)

    client.jobs.stage(b"\x00\x01", direct=True)

    assert "Authorization" not in mocked.calls[1].request.headers


def test_stage_upload_failure(client, mocked):
    signed = "https://storage.googleapis.com/bucket/imp1"
    mocked.post(f"{API}/imports/stage", json={"importId": "i", "uploadUrl": signed})
    mocked.put(signed, status=403, body="Forbidden")

    with pytest.raises(APIError):
        client.jobs.stage("x")


# ----------------------------------------------------------------------
# bulk_import
# ----------------------------------------------------------------------

SCHEMA = FormSchema(
    "Households",
    [
        TextField("Head", code="head", key=True, id="fhead"),
        QuantityField("Members", code="members", id="fmembers"),
        SingleSelectField(
            "Status", [SelectOption("Displaced", id="dis")], code="status", id="fstatus"
        ),
        MultiSelectField(
            "Needs",
            [SelectOption("Food", id="food"), SelectOption("Water", id="water")],
            code="needs",
            id="fneeds",
        ),
        DateField("Visit", code="visit", id="fvisit"),
        GeoPointField("Location", code="location", id="floc"),
    ],
    id="fma1",
    database_id="db1",
)


def import_mocks(mocked, existing=None):
    mocked.get(f"{API}/form/fma1/schema", json=SCHEMA.to_api())
    rows = existing or {}
    mocked.post(
        f"{API}/query/columns",
        json=columns_response(_id=list(rows.values()), k0=list(rows)),
    )
    mocked.post(
        f"{API}/imports/stage",
        json={"importId": "imp1", "uploadUrl": "/resources/imports/imp1"},
    )
    mocked.put(f"{API}/imports/imp1")
    mocked.post(f"{API}/jobs", json=job_status("COMPLETED"))


def uploaded_lines(mocked):
    upload = next(c for c in mocked.calls if c.request.method == "PUT")
    return upload.request.body.decode().split("\n")


def test_bulk_import_file_format_matches_r_package(db, mocked):
    from datetime import date

    import_mocks(mocked)

    job = db.form("fma1").records.bulk_import(
        [
            {
                "head": "Alice",
                "members": 5,
                "status": "Displaced",
                "needs": ["Food", "Water"],
                "visit": date(2024, 3, 1),
            },
            {"_id": "r2", "head": "Bob", "members": None},
        ]
    )

    lines = uploaded_lines(mocked)
    assert lines[:3] == [
        "LINE DELIMITED JSON RECORDS",
        "2",
        '["fhead", "fmembers", "fstatus", "fneeds", "fvisit"]',
    ]
    assert json.loads(lines[3]) == [
        None,
        "Alice",
        5,
        "dis",
        ["food", "water"],
        "2024-03-01",
    ]
    assert json.loads(lines[4]) == ["r2", "Bob", None, None, None, None]
    job_request = sent_json(mocked)
    assert job_request["type"] == "importRecords"
    assert job_request["descriptor"] == {"formId": "fma1", "importId": "imp1"}
    assert job.completed


def test_bulk_import_updates_records_with_matching_keys(db, mocked):
    import_mocks(mocked, existing={"Alice": "r1"})

    db.form("fma1").records.bulk_import(
        [{"head": "Alice", "members": 6}, {"head": "Zoe"}]
    )

    lines = uploaded_lines(mocked)
    assert json.loads(lines[3])[0] == "r1"
    assert json.loads(lines[4])[0] is None


def test_bulk_import_without_key_matching(db, mocked):
    mocked.get(f"{API}/form/fma1/schema", json=SCHEMA.to_api())
    mocked.post(
        f"{API}/imports/stage",
        json={"importId": "i", "uploadUrl": "/resources/imports/i"},
    )
    mocked.put(f"{API}/imports/i")
    mocked.post(f"{API}/jobs", json=job_status("COMPLETED"))

    db.form("fma1").records.bulk_import([{"head": "Alice"}], match_keys=False)

    assert not [c for c in mocked.calls if c.request.url.endswith("/query/columns")]


def test_bulk_import_rejects_duplicate_keys(db, mocked):
    import_mocks(mocked)

    with pytest.raises(ValueError, match="Rows 1 and 3 have the same key"):
        db.form("fma1").records.bulk_import(
            [{"head": "A"}, {"head": "B"}, {"head": "A"}]
        )
    mocked.reset()


def test_bulk_import_rejects_unsupported_fields(db, mocked):
    mocked.get(f"{API}/form/fma1/schema", json=SCHEMA.to_api())

    with pytest.raises(ValueError, match="use add_many"):
        db.form("fma1").records.bulk_import([{"location": (1.0, 2.0)}])
    with pytest.raises(KeyError, match="no field"):
        db.form("fma1").records.bulk_import([{"age": 1}])
    with pytest.raises(ValueError, match="no fields"):
        db.form("fma1").records.bulk_import([{"_id": "r1"}])


def test_bulk_import_subform_rows_carry_the_parent(db, mocked):
    subform = FormSchema("Members", [TextField("Name", id="fname")], id="sfhh")
    mocked.get(f"{API}/form/sfhh/schema", json=subform.to_api())
    mocked.post(
        f"{API}/imports/stage",
        json={"importId": "i", "uploadUrl": "/resources/imports/i"},
    )
    mocked.put(f"{API}/imports/i")
    mocked.post(f"{API}/jobs", json=job_status("COMPLETED"))

    db.form("sfhh").records.bulk_import(
        [{"Name": "Rami", "_parent": "p1"}, {"Name": "Lina"}], parent="p2"
    )

    lines = uploaded_lines(mocked)
    assert json.loads(lines[3]) == [None, "p1", "Rami"]
    assert json.loads(lines[4]) == [None, "p2", "Lina"]


def test_bulk_import_from_dataframe(db, mocked):
    pd = pytest.importorskip("pandas")
    import_mocks(mocked)

    db.form("fma1").records.bulk_import(
        pd.DataFrame({"head": ["A", "B"], "members": [1.0, float("nan")]})
    )

    lines = uploaded_lines(mocked)
    assert json.loads(lines[3]) == [None, "A", 1.0]
    assert json.loads(lines[4]) == [None, "B", None]


# ----------------------------------------------------------------------
# Exports, duplication, XLSForm
# ----------------------------------------------------------------------


def export_mocks(mocked):
    mocked.post(f"{API}/jobs", json=job_status("COMPLETED", jobResult=EXPORT_RESULT))
    mocked.get(f"{API}/jobs/j1/e1/Households.csv", body=b"csv")


def test_table_export(db, mocked, tmp_path):
    mocked.get(f"{API}/form/fma1/schema", json=SCHEMA.to_api())
    export_mocks(mocked)

    path = (
        db.form("fma1")
        .table()
        .select("head", "members")
        .where(head="Alice")
        .sort("members", desc=True)
        .export("csv", tmp_path)
    )

    request = sent_json(mocked, 1)
    assert request["type"] == "exportForm"
    descriptor = request["descriptor"]
    assert descriptor["format"] == "CSV"
    assert isinstance(descriptor["utcOffset"], int)
    (model,) = descriptor["tableModels"]
    assert model["formId"] == "fma1"
    assert model["columns"] == [
        {"id": "c0", "label": "_id", "formula": "_id", "translate": False},
        {"id": "c1", "label": "head", "formula": "fhead", "translate": False},
        {"id": "c2", "label": "members", "formula": "fmembers", "translate": False},
    ]
    assert model["ordering"] == [{"formula": "fmembers", "ascending": False}]
    assert model["filter"] == 'head == "Alice"'
    assert path.read_bytes() == b"csv"


def test_table_export_rejects_windows(db):
    with pytest.raises(ValueError, match="offset/limit"):
        db.form("fma1").table().limit(5).export()


def test_database_export(db, mocked, tmp_path):
    export_mocks(mocked)

    path = db.export("csv", tmp_path, folder=db.folder("fadmin"), filter="x > 1")

    descriptor = sent_json(mocked, 0)["descriptor"]
    assert descriptor == {
        "databaseId": "db1",
        "format": "WIDE",
        "fileFormat": "CSV",
        "includeBlanks": False,
        "utcOffset": descriptor["utcOffset"],
        "folderId": "fadmin",
        "filter": "x > 1",
    }
    assert path.name == "Households.csv"


def test_duplicate_database(db, mocked, tree_data):
    mocked.post(
        f"{API}/jobs", json=job_status("COMPLETED", jobResult={"databaseId": "db2"})
    )
    mocked.get(f"{API}/databases/db2", json=dict(tree_data, databaseId="db2"))

    copy = db.duplicate("Copy", records=True)

    assert sent_json(mocked, 0)["descriptor"] == {
        "templateDatabaseId": "db1",
        "databaseLabel": "Copy",
        "duplicateRecords": True,
    }
    assert copy.id == "db2"


def test_duplicate_into_existing_database(client, mocked, tree_data):
    mocked.post(
        f"{API}/jobs",
        json=job_status("COMPLETED", jobResult={"databaseId": "db1", "folderId": "f9"}),
    )
    mocked.get(f"{API}/databases/db1", json=tree_data)

    client.databases.duplicate("db0", "Imported", into="db1")

    assert sent_json(mocked, 0)["descriptor"]["targetDatabaseId"] == "db1"


def test_import_xlsform(db, mocked, tree_data, tmp_path):
    xlsx = tmp_path / "survey.xlsx"
    xlsx.write_bytes(b"PK\x03\x04")
    mocked.post(
        f"{API}/imports/stage",
        json={"importId": "x1", "uploadUrl": "/resources/imports/x1"},
    )
    mocked.put(f"{API}/imports/x1")
    mocked.post(
        f"{API}/jobs", json=job_status("COMPLETED", jobResult={"formId": "fmreg"})
    )
    mocked.get(f"{API}/databases/db1", json=tree_data)

    form = db.import_xlsform(xlsx, parent=db.folder("Admin boundaries"))

    assert mocked.calls[1].request.body == b"PK\x03\x04"
    assert "spreadsheetml" in mocked.calls[1].request.headers["Content-Type"]
    assert sent_json(mocked, 2)["descriptor"] == {
        "databaseId": "db1",
        "parentId": "fadmin",
        "importId": "x1",
    }
    assert form.id == "fmreg"


# ----------------------------------------------------------------------
# Audit log
# ----------------------------------------------------------------------


def event(ms, **extra):
    return {
        "time": ms,
        "type": "RECORD",
        "user": {"id": 7, "name": "A", "email": "a@x"},
        **extra,
    }


def test_audit_log_pages_backwards(db, mocked):
    mocked.post(
        f"{API}/databases/db1/audit",
        json={
            "events": [event(3000), event(2500)],
            "moreEvents": True,
            "startTime": 4000,
            "endTime": 2000,
        },
    )
    mocked.post(
        f"{API}/databases/db1/audit",
        json={
            "events": [event(1500), event(500)],
            "moreEvents": False,
            "startTime": 2000,
            "endTime": 0,
        },
    )

    events = db.audit_log(
        before=datetime.fromtimestamp(4, tz=UTC),
        after=datetime.fromtimestamp(1, tz=UTC),
        types=["RECORD"],
        resource=db.form("fma1"),
    )

    first, second = sent_json(mocked, 0), sent_json(mocked, 1)
    assert first == {
        "resourceFilter": "fma1",
        "typeFilter": ["RECORD"],
        "startTime": 4000,
    }
    assert second["startTime"] == 2000
    assert [e.raw["time"] for e in events] == [3000, 2500, 1500]
    assert events[0].user_email == "a@x"
    assert events[0].time == datetime.fromtimestamp(3, tz=UTC)
    assert events[0].to_dict()["user.id"] == "7"


def test_audit_log_limit_and_validation(db, mocked):
    mocked.post(
        f"{API}/databases/db1/audit",
        json={
            "events": [event(3000), event(2000)],
            "moreEvents": True,
            "endTime": 1000,
        },
    )

    assert len(db.audit_log(limit=1)) == 1
    with pytest.raises(ValueError, match="Unknown audit event types"):
        db.audit_log(types=["NOPE"])
    with pytest.raises(ValueError, match="limit"):
        db.audit_log(limit=0)
