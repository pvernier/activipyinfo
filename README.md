# ActiviPyInfo

**IMPORTANT**: This is a work in progress and not yet ready for production use.

ActiviPyInfo is a Python API for [ActivityInfo](https://www.activityinfo.org/)


## Dependencies

Currently, the only dependency is [`requests`](https://requests.readthedocs.io/).

To install it, run:

```bash
$ pip install requests
```

## Usage

Start by importing the necessary classes and initializing the `Manager` object with your API token.

```python

from activipyinfo import Field, Manager, Record

MY_TOKEN = "XXXX"

ai = Manager(MY_TOKEN)

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

record_1 was `["LBN001", "Mount Lebanon"]`. We are Updating it to `[`"LBN003", El Nabatieh"]`.

```python
my_form.update_record(record_1, ["LBN003", "El Nabatieh"])
```

Now the reference of "LBN001" has also been updated in the admin2 form to "LBN003".
