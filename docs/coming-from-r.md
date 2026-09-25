# Coming from the R package

activipyinfo follows the [ActivityInfo R package](https://www.activityinfo.org/support/docs/R/index.html):
same concepts, and the same payloads sent to the server. This page maps R
functions to their Python equivalents.

In the examples, `client = Client()`, `db = client.databases.get("<database id>")`
and `form = db.form("<form label or id>")`.

## Setup

| R | Python |
|---|---|
| `activityInfoToken("...")` | `Client("...")`, or set `ACTIVITYINFO_TOKEN` |
| `activityInfoRootUrl("https://...")` | `Client(base_url="https://...")`, or set `ACTIVITYINFO_BASE_URL` |
| `cuid()` | `cuid()` |

## Databases

| R | Python |
|---|---|
| `getDatabases()` | `client.databases.list()` |
| `getDatabaseTree(databaseId)` | `client.databases.get(database_id)` (then `db.resources`, `print(db.tree())`) |
| `getDatabaseResources(databaseId)` | `db.resources`, `db.folders`, `db.forms` |
| `addDatabase(label)` | `client.databases.create(label)` |
| `deleteDatabase(databaseId)` | `db.delete()` |
| `queryAuditLog(databaseId, ...)` | `db.audit_log(before=..., after=..., types=[...], limit=...)` |

## Users and roles

| R | Python |
|---|---|
| `getDatabaseUsers(databaseId)` | `db.users.list()` (`db.users.to_pandas()` for a data frame) |
| `getDatabaseUser(databaseId, userId)` | `db.users.get(user_id_or_email)` |
| `addDatabaseUser(databaseId, email, name, roleId = ..., roleParameters = ..., roleResources = ...)` | `db.users.add(email, name, role, parameters={...}, resources=[...])` |
| `updateUserRole(databaseId, userId, roleAssignment(...))` | `db.users.set_role(user, role, parameters={...}, resources=[...])` |
| `deleteDatabaseUser(databaseId, userId)` | `db.users.remove(user)` |
| `getDatabaseRoles(databaseId)` | `db.roles` (a list of `Role`) |
| `role(id, label, parameters, grants, permissions)` | `Role(label, grants=[...], parameters=[...], permissions=[...], id=...)` |
| `grant(resourceId, permissions, optional)` | `Grant(resource, permissions, optional=...)` |
| `resourcePermissions(view = TRUE, edit_record = "formula", ...)` | `resource_permissions(view=True, edit_record="formula", ...)` |
| `databasePermissions(manage_users = TRUE, ...)` | `database_permissions(manage_users=True, ...)` |
| `parameter(id, label, range)` | `RoleParameter(id, label, range)` |
| `addRole(databaseId, role)` / `updateRole(databaseId, role)` | `db.roles.add(role)` / `db.roles.update(role)` |
| `deleteRoles(databaseId, roleIds)` | `db.roles.delete(role)` |
| `getBillingAccount(id)`, `getBillingAccountUsers(id)`, ... | `client.billing.get(id)`, `client.billing.users(id)`, ... |

## Forms and fields

| R | Python |
|---|---|
| `getFormSchema(formId)` | `form.schema()` |
| `as.data.frame(schema)` | `schema.describe()`, `schema.to_pandas()` |
| `formSchema(databaseId, label, elements = list(...))` | `FormSchema(label, [...])` |
| `addForm(schema, parentId = folderId)` | `db.add_form(schema, parent=folder)` or `folder.add_form(schema)` |
| `updateFormSchema(schema)` | `form.update_schema(schema)` |
| `addFormField(formId, field)` | `form.add_field(field, after=...)` |
| `deleteFormField(formId, code = ...)` | `form.delete_field(code_or_id_or_label)` |
| `deleteForm(databaseId, formId)` | `form.delete()` |
| `relocateForm(formId, newDatabaseId)` | `form.relocate(database)` |
| `getFormTree(formId)` | `client.forms.tree(form_id)` |
| `createFormSchemaFromData(df, databaseId, label, keyColumns = ...)` | `FormSchema.from_data(df, label, keys=[...])` |
| `textFieldSchema(label, code = ...)` | `TextField(label, code=...)` |
| `barcodeFieldSchema(...)` | `TextField(..., barcode=True)` |
| `multilineFieldSchema(...)` | `MultilineField(...)` |
| `quantityFieldSchema(..., units = ...)` | `QuantityField(..., units=...)` |
| `dateFieldSchema`, `weekFieldSchema`, `monthFieldSchema` | `DateField`, `WeekField`, `MonthField` |
| `singleSelectFieldSchema(..., options = c(...))` | `SingleSelectField(..., [...])` |
| `multipleSelectFieldSchema(...)` | `MultiSelectField(...)` |
| `referenceFieldSchema(..., referencedFormId = ...)` | `ReferenceField(..., form)` |
| `userFieldSchema(..., databaseId = ...)` | `UserField(..., database)` |
| `subformFieldSchema(..., subformId = ...)` | `SubformField(..., subform)` (or `form.add_subform(...)`) |
| `calculatedFieldSchema(..., formula = ...)` | `CalculatedField(..., formula)` |
| `serialNumberFieldSchema(...)` | `SerialNumberField(...)` |
| `geopointFieldSchema(...)` | `GeoPointField(...)` |
| `attachmentFieldSchema(...)` | `AttachmentField(...)` |
| `sectionFieldSchema(...)` | `SectionHeader(...)` |

## Records

In R, record values are keyed by field code or id and passed as they are.
In Python they can also be keyed by label, and are checked and converted
with the form's schema (select labels, `datetime.date`, records as
references, `(latitude, longitude)` points).

| R | Python |
|---|---|
| `getRecord(formId, recordId)` | `form.records.get(record_id)` |
| `recordExists(formId, recordId)` | `form.records.exists(record_id)` |
| `addRecord(formId, fieldValues = list(...), parentRecordId = ...)` | `form.records.add({...}, parent=...)` |
| `updateRecord(formId, recordId, fieldValues)` | `form.records.update(record, {...})` |
| `deleteRecord(formId, recordId)` | `form.records.delete(record)` |
| `recoverRecord(formId, recordId)` | `form.records.recover(record)` |
| `getRecordHistory(formId, recordId)` | `form.records.history(record)` |
| `reference(formId, recordId)` | the record id, or `form.records.ref(key=value)` |
| `importRecords(formId, data)` | `form.records.bulk_import(df)` |
| `submitPending()` | not available yet |

## Querying

| R | Python |
|---|---|
| `getRecords(formId)` | `form.table()` |
| `... %>% filter(Status == "Open")` | `.where(status="Open")` or `.filter('status == "Open"')` |
| `... %>% select(...)` | `.select("code", name="formula")` |
| `... %>% arrange(desc(x))` | `.sort("x", desc=True)` |
| `... %>% slice_head(n = 10)` / `adjustWindow(...)` | `.limit(10)` / `.offset(n)` |
| `... %>% collect()` | `.collect()` or `.to_pandas()` |
| `queryTable(formId, columns, filter = ...)` | `client.queries.columns(form_id, {...}, filter=...)` |
| `columnStyle(columnNames = "code")` | `form.table(names="code")` |
