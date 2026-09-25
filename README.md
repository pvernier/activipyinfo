# ActiviPyInfo

**IMPORTANT**: This is a work in progress and not yet ready for production use.

ActiviPyInfo is a Python API for [ActivityInfo](https://www.activityinfo.org/)


## Installation

The only runtime dependency is [`requests`](https://requests.readthedocs.io/).

```bash
pip install git+https://github.com/pvernier/activipyinfo.git
```

## Authentication

Create a personal API token in your ActivityInfo account settings, then either
pass it explicitly or set the `ACTIVITYINFO_TOKEN` environment variable.
For a self-managed server, pass `base_url=...` or set `ACTIVITYINFO_BASE_URL`.

```python
from activipyinfo import Client

client = Client()  # reads ACTIVITYINFO_TOKEN
client = Client("XXXX")  # or pass the token
client.get("databases")  # low-level call to GET /resources/databases
```

API errors raise subclasses of `activipyinfo.APIError` (`AuthenticationError`,
`NotFoundError`, `PermissionDeniedError`, ...) that carry the HTTP status and
the error code returned by ActivityInfo. Rate-limited and temporarily
unavailable requests are retried automatically.

## Your account

With an OAuth access token (ActivityInfo refuses this request for personal
API tokens):

```python
me = client.me()
print(me.name, me.email, me.billing_account_id)
```

## Databases

```python
for db in client.databases.list():
    print(db.id, db.label)

db = client.databases.get("ck8oykh8m5")  # by id, with its full tree
db = client.databases.find("Lebanon response")  # by exact label

new_db = client.databases.create("Lebanon response", description="2026 plan")
new_db.delete()  # only the owner can delete

db.billing_account().plan_name
```

## Folders and the resource tree

A database's folders, forms, subforms and reports are loaded the first time
you need them (`db.refresh()` reloads them).

```python
print(db.tree())
# Lebanon response (ck8oykh8m5)
# ├── Admin boundaries [folder c1a2...]
# │   ├── Admin1 [form c3b4...]
# │   └── Admin2 [form c5d6...]
# └── Registration [form c7e8...]

db.folders, db.forms, db.children  # lists of Folder / Form
admin = db.folder("Admin boundaries")  # by label or id
form = db.form("Admin1")  # MultipleMatchesError if the label is not unique
form = db.find("Admin1", parent=admin)  # so narrow the search down

folder = db.add_folder("Lebanon")  # at the database root
archive = folder.add_folder("Archive")  # nested folder
archive.rename("Old data")
archive.move(db)  # back to the root
archive.delete()
```

Several changes can be sent in one request with `DatabaseChanges`:

```python
from activipyinfo import DatabaseChanges

changes = DatabaseChanges()
changes.delete_resource(db.form("Old form"))
changes.add_language("fr")
db.apply(changes)
```

## Roles and permissions

Roles follow the R package: a role has **grants** (permissions on a
resource), optional database-wide **permissions**, and **parameters** whose
per-user values can be used in formulas as `@user.<id>`.

```python
from activipyinfo import Grant, Role, RoleParameter, resource_permissions

partners = db.form("Partners")
role = Role(
    "Reporting partner",  # id derived: "reportingpartner"
    grants=[
        Grant(db, resource_permissions()),  # view everything
        Grant(
            db.folder("Reporting"),
            resource_permissions(
                add_record=True,
                edit_record="[partner] == @user.partner",  # record-level rule
            ),
            optional=True,  # only for users assigned to it
        ),
    ],
    parameters=[RoleParameter("partner", "Partner", partners)],
)
db.roles.add(role)  # or db.roles.update(role)

[r.label for r in db.roles]
db.roles.get("Reporting partner")  # by id or label
db.roles.delete("Reporting partner")
```

## Users

Users can be referred to by email or id, and roles by object, id or label.

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
db.users.get("alice@example.org").grants
db.users.remove("alice@example.org")

client.users.list("ck8oykh8m5")  # same methods, by database id
```

## Billing account (read-only)

```python
account_id = db.billing_account_id
client.billing.get(account_id)
client.billing.users(account_id, owners_only=False)
client.billing.databases(account_id)  # usage counts per database
client.billing.domains(account_id)
```

With an OAuth token, `account_id` can be left out to use your own billing
account.

## Forms and fields

There is one class per field type, modelled on the R package's builders:
`TextField`, `MultilineField`, `QuantityField`, `DateField`, `WeekField`,
`MonthField`, `SingleSelectField`, `MultiSelectField`, `ReferenceField`,
`MultiReferenceField`, `UserField`, `SubformField`, `CalculatedField`,
`SerialNumberField`, `GeoPointField`, `AttachmentField`, `SectionHeader` and
`NoteField`.

```python
from activipyinfo import (
    FormSchema,
    QuantityField,
    ReferenceField,
    SelectOption,
    SingleSelectField,
    TextField,
)

folder = db.folder("Admin boundaries")
provinces = folder.add_form(
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
            ReferenceField("Province", provinces, code="province"),
            TextField("Head of household", code="head", key=True),
            QuantityField("Members", code="members", units="people"),
            SingleSelectField("Status", ["Resident", "Displaced"], code="status"),
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
schema.describe()  # one dict per field, like as.data.frame() in R

households.add_field(TextField("Phone", code="phone"), after="head")
households.delete_field("phone")  # recover with households.recover_field(id)

schema = households.schema()
schema["status"].options.append(SelectOption("Returned"))
households.update_schema(schema)

households.duplicate()  # structure only, no records
households.relocate(other_db)  # with subforms and records
```

Schemas keep any property the library does not model, so reading a schema
and sending it back never loses information.

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
