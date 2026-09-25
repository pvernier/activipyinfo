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
form = db.form("Admin1")  # raises MultipleMatchesError
form = db.find("Admin1", parent=admin)  #   if the label is not unique

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
    "Reporting partner",                         # id derived: "reportingpartner"
    grants=[
        Grant(db, resource_permissions()),       # view everything
        Grant(
            db.folder("Reporting"),
            resource_permissions(
                add_record=True,
                edit_record="[partner] == @user.partner",  # record-level rule
            ),
            optional=True,                       # only for users assigned to it
        ),
    ],
    parameters=[RoleParameter("partner", "Partner", partners)],
)
db.roles.add(role)                               # or db.roles.update(role)

[r.label for r in db.roles]
db.roles.get("Reporting partner")                # by id or label
db.roles.delete("Reporting partner")
```

## Users

Users can be referred to by email or id, and roles by object, id or label.

```python
for user in db.users.list():
    print(user.email, user.role.role_id, user.last_login_time)

db.users.add(
    "alice@example.org", "Alice", "Reporting partner",
    resources=[db.folder("Reporting")],          # default: the whole database
    parameters={"partner": "<partner record id>"},
)
db.users.set_role("alice@example.org", "Read only")
db.users.get("alice@example.org").grants
db.users.remove("alice@example.org")

client.users.list("ck8oykh8m5")                  # same methods, by database id
```

## Billing account (read-only)

```python
client.billing.get()                             # defaults to your own account
client.billing.users(owners_only=False)
client.billing.databases()                       # usage counts per database
client.billing.domains()
```

## Forms and records (legacy API)

Creating forms and records still uses the original object API until the new
one lands (phases 3 and 4 of [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md)).
`Manager` is deprecated and will be removed at that point.

```python
from activipyinfo import Field, Manager, Record

ai = Manager()  # reads ACTIVITYINFO_TOKEN
my_db = ai.get_db("mydbuid")
my_folder = my_db.create_folder("Lebanon")
```

## Create a form

```python
field1 = Field(
    {
        "code": "pcode",
        "label": "P-code",
        "description": "P-code of the admin1",
        "required": True,
        "type": "FREE_TEXT",
        "key": True,
    }
)

field2 = Field(
    {
        "code": "name",
        "label": "Name",
        "description": "Name of the admin1",
        "required": True,
        "type": "FREE_TEXT",
        "key": False,
    }
)

fields = [field1, field2]

my_form = my_folder.create_form("Admin1", fields)

print(my_form)
# Form(iv918zrz0d5ybk7e, Admin1, e5r12b568bic7doi)
```

At this stage the form is empty, we need to add records

## Add records

```python
record_1 = Record([field1, field2], ["LBN001", "Mount Lebanon"])
record_2 = Record([field1, field2], ["LBN002", "Bekaa"])

my_form.add_record(record_1)
my_form.add_record(record_2)
```

## Delete a record

```python
my_form.delete_record(record_2)
```

## Add a new form with a reference to the first form

```python
field3 = Field(
    {
        "code": "pcode",
        "label": "P-code",
        "description": "P-code of the admin2",
        "required": True,
        "type": "FREE_TEXT",
        "key": True,
    }
)

field4 = Field(
    {
        "code": "name",
        "label": "Name",
        "description": "Name of the admin2",
        "required": True,
        "type": "FREE_TEXT",
        "key": False,
    }
)

field5 = Field(
    {
        "code": "admin1",
        "label": "Admin1",
        "description": "Pcode of the admin1",
        "required": True,
        "type": "reference",
        "key": False,
        "reference": my_form,
    }
)

fields2 = [field3, field4, field5]

my_form2 = my_folder.create_form("Admin2", fields2)
```

## Add records to the second form

```python
record_3 = Record([field3, field4, field5], ["LBN001001", "Metn", "LBN001"])
record_4 = Record([field3, field4, field5], ["LBN001002", "Zahleh", "LBN001"])
record_5 = Record([field3, field4, field5], ["LBN001003", "Rachaiya", "LBN001"])

my_form2.add_record(record_3)
my_form2.add_record(record_4)
my_form2.add_record(record_5)
```

## Update a record which is a reference

record_1 was `["LBN001", "Mount Lebanon"]`. We are updating it to `["LBN003", "El Nabatieh"]`.

```python
my_form.update_record(record_1, ["LBN003", "El Nabatieh"])
```

Now the reference of "LBN001" has also been updated in the admin2 form to "LBN003".

## Development

```bash
uv sync                                  # install the package and dev tools
uv run pytest                            # unit tests (HTTP is mocked)
ACTIVITYINFO_TOKEN=... uv run pytest -m integration   # read-only live API checks
ACTIVITYINFO_TOKEN=... ACTIVITYINFO_ALLOW_WRITES=1 uv run pytest -m integration  # also creates/deletes a scratch database
# ACTIVITYINFO_TEST_EMAIL=you@example.org also tests inviting a user (sends an email)
uv run ruff check . && uv run ruff format --check . && uv run mypy
```
