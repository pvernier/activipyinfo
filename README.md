# activipyinfo

[![CI](https://github.com/pvernier/activipyinfo/actions/workflows/ci.yml/badge.svg)](https://github.com/pvernier/activipyinfo/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/activipyinfo)](https://pypi.org/project/activipyinfo/)
[![Python](https://img.shields.io/pypi/pyversions/activipyinfo)](https://pypi.org/project/activipyinfo/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](https://github.com/pvernier/activipyinfo/blob/main/LICENSE)

A Python client for the [ActivityInfo](https://www.activityinfo.org/) API:
databases, folders, users and roles, forms, records, queries, imports and
exports, with optional pandas support.

It follows the [ActivityInfo R package](https://www.activityinfo.org/support/docs/R/index.html):
same concepts and the same payloads sent to the server. If you know the R
package, see [Coming from R](https://github.com/pvernier/activipyinfo/blob/main/docs/coming-from-r.md).

> **Status: alpha.** The API may still change before version 1.0; see the
> [changelog](https://github.com/pvernier/activipyinfo/blob/main/CHANGELOG.md).

## Installation

```bash
pip install activipyinfo            # needs Python 3.12+
pip install "activipyinfo[pandas]"  # with DataFrame support
```

## Quickstart

Create a personal API token in your ActivityInfo account settings and put it
in the `ACTIVITYINFO_TOKEN` environment variable.

```python
from activipyinfo import Client, QuantityField, SingleSelectField, TextField

client = Client()  # reads ACTIVITYINFO_TOKEN
db = client.databases.get("<database id>")
print(db.tree())  # the database's folders and forms

households = db.add_form(
    "Households",
    [
        TextField("Head of household", code="head", key=True),
        QuantityField("Members", code="members"),
        SingleSelectField("Status", ["Resident", "Displaced"], code="status"),
    ],
)
households.records.add_many(
    [
        {"head": "Alice", "members": 5, "status": "Displaced"},
        {"head": "Bob", "members": 2, "status": "Resident"},
    ]
)

households.table().where(status="Displaced").to_pandas()
```

## Guide

- [Connecting](#connecting)
- [Databases and folders](#databases-and-folders)
- [Forms and fields](#forms-and-fields)
- [Records](#records)
- [Tables and DataFrames](#tables-and-dataframes)
- [Imports, exports and other jobs](#imports-exports-and-other-jobs)
- [Users and roles](#users-and-roles)
- [Billing accounts](#billing-accounts)
- [Errors](#errors)

### Connecting

```python
from activipyinfo import Client

client = Client()  # token from ACTIVITYINFO_TOKEN
client = Client("<token>")  # or passed explicitly
client = Client(base_url="https://activityinfo.example.org")  # self-managed server
```

`ACTIVITYINFO_BASE_URL` can also set the server. Requests that are rate
limited or hit a temporarily unavailable server are retried automatically.

`client.me()` returns your own account, but ActivityInfo only answers it for
OAuth access tokens, not personal API tokens. Any endpoint can also be called
directly: `client.get("databases")`, `client.post(...)`.

### Databases and folders

```python
for db in client.databases.list():
    print(db.id, db.label)

db = client.databases.get("<database id>")  # with its folders, forms, roles
db = client.databases.find("Lebanon response")  # by exact label
new_db = client.databases.create("Lebanon response", description="2026 plan")
```

A database's resources are loaded the first time you need them
(`db.refresh()` reloads them). Folders and forms can be found by label or id:

```python
print(db.tree())
# Lebanon response (ck8oykh8m5)
# ├── Admin boundaries [folder c1a2...]
# │   ├── Provinces [form c3b4...]
# │   └── Districts [form c5d6...]
# └── Households [form c7e8...]

admin = db.folder("Admin boundaries")
provinces = db.form("Provinces")  # MultipleMatchesError if the label is not unique
provinces = db.find("Provinces", parent=admin)  # so narrow the search down
db.folders, db.forms  # all folders and forms

archive = admin.add_folder("Archive")  # folders can be nested
archive.rename("Old data")
archive.move(db)  # to the database root
archive.delete()
```

`DatabaseChanges` sends several changes (resources, roles, locks, languages)
in one request: `db.apply(changes)`.

### Forms and fields

There is one class per field type, modelled on the R package's builders:
`TextField`, `MultilineField`, `QuantityField`, `DateField`, `WeekField`,
`MonthField`, `SingleSelectField`, `MultiSelectField`, `ReferenceField`,
`MultiReferenceField`, `UserField`, `SubformField`, `CalculatedField`,
`SerialNumberField`, `GeoPointField`, `AttachmentField`, `SectionHeader` and
`NoteField`.

```python
from activipyinfo import (
    DateField,
    FormSchema,
    QuantityField,
    ReferenceField,
    SelectOption,
    SingleSelectField,
    TextField,
)

provinces = admin.add_form(
    "Provinces",
    [
        TextField("P-code", code="pcode", key=True),
        TextField("Name", code="name", required=True),
    ],
)
households = db.add_form(
    FormSchema(
        "Households",
        [
            TextField("Head of household", code="head", key=True),
            ReferenceField("Province", provinces, code="province"),
            QuantityField("Members", code="members", units="people"),
            SingleSelectField("Status", ["Resident", "Displaced"], code="status"),
            DateField("Visit date", code="visit"),
        ],
    )
)
members = households.add_subform("Members", [TextField("Name", code="name")])
```

Reading and changing a schema:

```python
schema = households.schema()
print(schema)  # one line per field: code, type, label
schema["members"].units  # fields by code, id or label
schema.describe()  # one dict per field (schema.to_pandas() for a DataFrame)

households.add_field(TextField("Phone", code="phone"), after="head")
households.delete_field("phone")  # recover with households.recover_field(id)

schema = households.schema()
schema["status"].options.append(SelectOption("Returned"))
households.update_schema(schema)

households.duplicate()  # structure only, no records
households.relocate(other_db)  # with its subforms and records
```

Schemas keep every property the library does not model, so reading a schema
and sending it back never loses information.

### Records

`form.records` reads and writes records. Values are keyed by field code, id
or label, and are checked and converted with the form's schema: select
options by label, dates as `datetime.date`, references as a record or record
id, points as `(latitude, longitude)`, and `None` clears a field.

```python
from datetime import date

provinces.records.add_many(
    [
        {"pcode": "LBN001", "name": "Mount Lebanon"},
        {"pcode": "LBN002", "name": "Bekaa"},
    ]
)  # sent in batches of 200

household = households.records.add(
    head="Alice",
    province=provinces.records.ref(pcode="LBN002"),  # id of the matching record
    members=5,
    status="Displaced",
    visit=date(2024, 3, 1),
)
household["status"]  # "Displaced"
household.to_dict()  # {"head": "Alice", "province": "...", ...}

households.records.update(household, members=6, visit=None)
households.records.find(head="Alice")  # the one matching record
households.records.find_all(status="Displaced")  # matching record ids
households.records.list(filter="members > 5")  # records with all their fields
households.records.history(household)

members.records.add({"name": "Rami"}, parent=household)  # subform record

households.records.delete(household)
households.records.recover(household)
```

`add_many`, `update_many` (rows with an `"_id"` key) and `delete_many` send
changes in batches. If a batch fails, a `RecordBatchError` lists the records
already saved (`error.submitted`).

### Tables and DataFrames

`form.table()` describes a query, like `getRecords() |> filter() |> select()`
in R. Nothing is fetched until `collect()`, `first()`, `count()`,
`to_pandas()` or iteration.

```python
table = (
    households.table()
    .select("head", "members", province="province.name")  # fields or formulas
    .where(status="Displaced")  # field == value
    .filter("members > 2")  # any boolean formula
    .sort("members", desc=True)
    .limit(10)
)
table.collect()  # [{"_id": ..., "head": "Alice", "members": 5, "province": ...}]
table.count()
table.to_pandas()

households.to_pandas()  # every record, one column per field
households.to_pandas(names="code")  # columns named by field code
```

By default, columns are named after field labels, and a reference field is
shown as the key fields of the form it references ("Province P-code"). A
subform's table has a `_parent` column with the parent record id.

A form can be created from a DataFrame (or a list of dicts), like
`createFormSchemaFromData()` in R, and filled from it:

```python
schema = FormSchema.from_data(df, "People", keys=["Name"])
people = admin.add_form(schema)
people.records.add_many(df)  # NaN / None leave a field empty
```

### Imports, exports and other jobs

Heavy work runs as server-side jobs. These methods wait for the job to
finish; they accept `timeout=` and a `progress=` callback.

```python
# Large imports go through the server's import pipeline (like R
# importRecords). Rows whose key fields match an existing record update it.
people.records.bulk_import(df)

# Exports are downloaded to the current directory, or to a given path.
households.export("xlsx")  # every record
households.table().select("head", "members").where(status="Displaced").export("csv")
db.export("xlsx", folder=admin)  # several forms

db.import_xlsform("survey.xlsx", parent=admin)  # returns the new form
db.duplicate("Lebanon response (copy)", records=False)  # returns the new database
db.audit_log(limit=100, types=["RECORD"])  # most recent events first

job = client.jobs.run("exportForm", descriptor)  # any job type
job.download("out.csv")
```

### Users and roles

Roles follow the R package: a role has **grants** (permissions on a
resource), optional database-wide **permissions**, and **parameters** whose
per-user values can be used in formulas as `@user.<id>`.

```python
from activipyinfo import Grant, Role, RoleParameter, resource_permissions

partners = db.form("Partners")
role = Role(
    "Reporting partner",  # id derived from the label: "reportingpartner"
    grants=[
        Grant(db, resource_permissions()),  # view everything
        Grant(
            db.folder("Reporting"),
            resource_permissions(
                add_record=True,
                edit_record="[partner] == @user.partner",  # record-level rule
            ),
            optional=True,  # only for users assigned to this folder
        ),
    ],
    parameters=[RoleParameter("partner", "Partner", partners)],
)
db.roles.add(role)  # or db.roles.update(role)
db.roles.get("Reporting partner")  # by id or label
```

Users are referred to by email or id, and roles by object, id or label:

```python
for user in db.users.list():
    print(user.email, user.role.role_id, user.last_login_time)

db.users.add(
    "alice@example.org",
    "Alice",
    "Reporting partner",
    resources=[db.folder("Reporting")],  # default: the whole database
    parameters={"partner": "<partner record id>"},
)
db.users.set_role("alice@example.org", "Read only")
db.users.remove("alice@example.org")
db.users.to_pandas()
```

### Billing accounts

```python
account_id = db.billing_account_id
client.billing.get(account_id)
client.billing.users(account_id, owners_only=False)
client.billing.databases(account_id)  # usage counts per database
```

With an OAuth token, `account_id` can be left out to use your own account.

### Errors

Everything raised by the library derives from `ActivityInfoError`:

- `APIError` subclasses for HTTP errors (`AuthenticationError`,
  `PermissionDeniedError`, `NotFoundError`, `BadRequestError`, ...), with the
  status code and ActivityInfo's error code and message;
- `NoMatchError` / `MultipleMatchesError` when a lookup by label finds no or
  several matches;
- `RecordBatchError`, `JobFailedError` and `JobTimeoutError` for bulk writes
  and jobs.

## Development

```bash
uv sync         # install the package and dev tools
uv run pytest   # unit tests (HTTP is mocked)
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

Tests against the live API are opt-in and configured with environment
variables (PowerShell syntax shown; in bash, use `export NAME=value`):

```powershell
$env:ACTIVITYINFO_TOKEN = "..."           # read-only checks
$env:ACTIVITYINFO_ALLOW_WRITES = "1"      # also tests that change data...
$env:ACTIVITYINFO_TEST_DATABASE = "..."   # ...in a scratch folder of this database
$env:ACTIVITYINFO_TEST_EMAIL = "..."      # also invite a user (sends an email)
uv run pytest -m integration
```

Write tests create a scratch folder (deleted afterwards) in the database
given by `ACTIVITYINFO_TEST_DATABASE`. Without it, they create a scratch
database, which only works for accounts allowed to create databases.

### Releasing

1. Update the version in `activipyinfo/__version__.py` and the
   [changelog](https://github.com/pvernier/activipyinfo/blob/main/CHANGELOG.md),
   and merge them into `main`.
2. Tag the merge commit and push the tag: `git tag v0.1.0 && git push origin v0.1.0`.

The release workflow checks that the tag matches the package version, runs
the checks and tests, publishes to PyPI and creates the GitHub release.
Running the workflow by hand (Actions → Release → Run workflow) publishes to
TestPyPI instead, as a dry run.

## License

[MIT](https://github.com/pvernier/activipyinfo/blob/main/LICENSE)
