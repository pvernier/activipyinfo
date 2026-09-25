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

## Usage

The object API below is being redesigned (see
[docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md)). `Manager` is a `Client`
with a few legacy helpers.

```python
from activipyinfo import Field, Manager, Record

ai = Manager("XXXX")  # or Manager() to read ACTIVITYINFO_TOKEN
```

## List databases

```python
dbs = ai.get_dbs()

for db in dbs:
    print(db.label)
```

## Identify a database

```python
MY_DB = "mydbuid"

my_db = ai.get_db(MY_DB)
print(my_db.label)

resources = my_db.get_resources()
print(resources)
```

## Create a folder

```python
my_folder = my_db.create_folder("Lebanon")
```

At this stage the folder is empty, we need to add a form.

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
uv run ruff check . && uv run ruff format --check . && uv run mypy
```
