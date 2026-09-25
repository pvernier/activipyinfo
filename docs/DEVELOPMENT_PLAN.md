# activipyinfo: development plan

Sources reviewed:
- ActivityInfo REST API reference: https://www.activityinfo.org/support/docs/api/index.html
- ActivityInfo R package reference: https://www.activityinfo.org/support/docs/R/index.html
- The current code in this repo (about 600 lines, plus the uncommitted `http.py` and `tests/`)

---

## 1. Assessment of the current code

### What works and is worth keeping
- Listing databases, reading database resources, creating a folder or a form, and adding or deleting a record work end to end.
- `http.py` already turns HTTP errors into `ActivityInfoAuthError`, `ActivityInfoNotFoundError` and `ActivityInfoError`.
- The payload templates in `folder.py` and `form.py` are useful examples of what the API expects.
- A first test suite exists: it mocks `requests` and checks how requests are built.

### Structural problems (fix before adding features)
| Problem | Where | Consequence |
|---|---|---|
| Global mutable state (`Constant.token`, `Constant.headers`) is copied into every object | `constant.py`, every class | You can't use two accounts or servers at once, the token is stored on every object, and objects created before `Manager()` have `headers=None` |
| Every object copies `token`, `headers`, `base_url` and `timeout` | all models | Duplication, and HTTP logic is mixed into the data models |
| No `requests.Session`, no retries, no backoff on 429 or 5xx | `http.py` | Slow, and bulk jobs fail on the first temporary error |
| The API's error body (`code`, `message`) is discarded | `http.py` | Error messages don't help users |
| `Manager.get_db()` lists every database and filters on the client | `manager.py` | Makes an extra call and returns `None` silently instead of raising. `GET /resources/databases/{id}` exists |
| `Field` is an untyped `dict` | `field.py` | No autocompletion or validation, and only `FREE_TEXT` and `reference` are handled |
| `Record` takes two parallel lists (`fields`, `values`) | `record.py` | Easy to misalign. The API accepts `{"fieldCode": value}` directly |
| Reference fields are resolved by downloading the whole referenced form and running `value in er.values()` | `form.py` `add_record` | O(N) per record and can match the wrong column. It also needs the `Field` objects from creation time |
| `update_record` is marked as not working | `form.py` | It doesn't resolve references (the cause of the bug) |
| No batching (the API limit is 200 changes per `/resources/update` call) | `form.py` | Can't do bulk inserts |
| Uses the old flat `/form/{id}/query` endpoint for reads | `form.py` | No column selection, filters or sorting |
| Leftover code: `mixins/` (only prints debug output), unused `Constant.token`, and commented-out templates | various | Noise |
| `pytest` is a runtime dependency, and the version is `0.1.0` in `pyproject.toml` but `0.0.1` in `__version__.py` | packaging | Packaging hygiene |

### Coverage compared with the API and the R package
| Area | API | R package | activipyinfo today |
|---|---|---|---|
| Account / me | `GET /accounts/status` | – | ✗ |
| Databases: list, get tree | ✓ | `getDatabases`, `getDatabaseTree`, `getDatabaseResources` | partial |
| Databases: create, update, delete | ✓ | `addDatabase`, `deleteDatabase` | ✗ |
| Folders | `POST /databases/{id}` (resourceUpdates) | – | create only (plus form deletion) |
| Database users | add, list, delete, role, grants, unlock, restore | `addDatabaseUser`, `getDatabaseUsers`, `updateUserRole`… | ✗ |
| Roles and permissions | via `roleUpdates` | `role()`, `grant()`, `resourcePermissions()`… | ✗ |
| Billing account | get account, users, databases, domains | `getBillingAccount*` | ✗ |
| Form schema: get, update | ✓ | `getFormSchema`, `updateFormSchema`, `formSchema` | get only |
| Typed field builders (about 18 types) | ✓ | `textFieldSchema`, `quantityFieldSchema`… | ✗ |
| Add, delete, relocate or duplicate a form | ✓ | `addForm`, `deleteForm`, `relocateForm` | add and delete only |
| Records CRUD | `/resources/update`, `getRecord`, `getRecordHistory`, recover | `addRecord`, `updateRecord`, `deleteRecord`, `getRecord`, `recordExists`… | partial and buggy |
| Queries | `/query/columns`, `/query/rows`, pivot | `getRecords` + `filter/select/collect`, `queryTable` | ✗ |
| Jobs (import, export, duplicate) | `/resources/jobs` + status + file | `importRecords`, `stageImport` | ✗ |
| Attachments | upload, get, status | `getAttachment` | ✗ |
| Audit log, reports, translations, search | ✓ | `queryAuditLog`, `queryReportResults` | ✗ |

---

## 2. Target design

### Principles
1. **One `Client` object holds all configuration.** No global state. The token can come from the `ACTIVITYINFO_TOKEN` environment variable, and `base_url` can be changed for self-managed servers.
2. **Two layers:**
   - A **service layer** that maps one method to one endpoint and returns typed models (`client.databases.get(id)`). It is predictable and easy to test.
   - A **convenience layer** on the models (`db.add_folder(...)`, `form.records.add({...})`). The models keep a reference to the client that created them.
3. **Typed models as dataclasses** with `from_api(dict)` / `to_api()`. They round-trip the API JSON without losing data, and unknown keys are kept in `raw`.
4. **Refer to things by code or label, not only by ID.** For example `db.forms["Admin1"]` and record dicts keyed by field code, which the API already accepts.
5. **Batching and pagination happen automatically.** `add_many` splits changes into batches of 200.
6. **pandas is an optional extra** (`pip install activipyinfo[pandas]`). The core only needs `requests`.

### Proposed layout
```
activipyinfo/
  __init__.py          # public API: Client, field classes, FormSchema, Role, exceptions
  client.py            # Client: Session, auth, base_url, timeout, retries, low-level get/post/put/delete
  exceptions.py        # error hierarchy (400/401/403/404/409/410/429/5xx), keeps the API's code and message
  ids.py               # cuid()
  models/
    account.py         # UserAccount
    database.py        # Database, Resource, Folder, Lock
    permissions.py     # Role, Permission, Operation (enum), RoleAssignment, Grant
    user.py            # DatabaseUser
    form.py            # Form (handle), FormSchema
    fields.py          # TextField, QuantityField, DateField, SingleSelect, Reference, Subform, Calculated, …
    record.py          # Record
    job.py             # Job
  services/
    accounts.py  databases.py  users.py  forms.py  records.py  queries.py  jobs.py  billing.py
  query.py             # QueryBuilder / Table (filter, select, sort, collect)
  _pandas.py           # optional to_pandas() / from DataFrame
```

### What using it should look like
```python
import activipyinfo as ai

client = ai.Client()                                  # reads ACTIVITYINFO_TOKEN
client.me()                                           # UserAccount

db = client.databases.create("Lebanon response")
folder = db.add_folder("Admin boundaries")

admin1 = folder.add_form(ai.FormSchema("Admin1", fields=[
    ai.TextField("pcode", "P-code", key=True, required=True),
    ai.TextField("name", "Name", required=True),
]))
admin1.records.add_many([
    {"pcode": "LBN001", "name": "Mount Lebanon"},
    {"pcode": "LBN002", "name": "Bekaa"},
])

admin2 = folder.add_form(ai.FormSchema("Admin2", fields=[
    ai.TextField("pcode", "P-code", key=True),
    ai.ReferenceField("admin1", "Admin1", form=admin1),
]))
admin2.records.add({"pcode": "LBN001001", "admin1": admin1.ref(pcode="LBN001")})

df = (admin2.table()
      .select("pcode", admin1_name="admin1.name")
      .filter("pcode == 'LBN001001'")
      .to_pandas())

role = ai.Role("Data entry", permissions=[
    ai.Permission(ai.Operation.VIEW),
    ai.Permission(ai.Operation.ADD_RECORD),
])
db.roles.add(role)
db.users.add("jane@example.org", "Jane", role=role, resources=[folder])
```

---

## 3. Step-by-step roadmap

Each phase ends with unit tests (mocked HTTP using `responses` and JSON fixtures copied from real API responses) plus a few **integration tests**. The integration tests are marked `@pytest.mark.integration` and run against a throwaway database using a token from an environment variable. They are skipped by default.

### Phase 0: Foundations (do this first; it unblocks everything else)

> **Status: done** on branch `phase-0-foundations`. Decisions made along the way:
> - The flat package layout is kept; moving to `src/` isn't worth the churn yet.
> - `Manager` is kept as a subclass of `Client` with its legacy helpers. It
>   gets deprecated in Phase 1, once `client.databases` replaces it.
> - Retries: a 429 is retried for every method. A 502/503/504 or a dropped
>   connection is retried only for idempotent methods (GET/PUT/DELETE), so a
>   POST such as starting a job is never sent twice.
1. Commit the current work in progress (`http.py` and `tests/`) so you have a baseline.
2. Packaging: fix the version to one source, move `pytest` into a `[dependency-groups] dev` group, add `ruff` and `mypy`, and consider a `src/` layout. Add a `py.typed` marker.
3. `Client`:
   - `requests.Session` that sends the `Authorization: Bearer` header
   - token from an argument or `ACTIVITYINFO_TOKEN`
   - `base_url` defaults to `https://www.activityinfo.org`, with every path under `/resources/…`
   - retries with exponential backoff on 429, 502, 503 and 504, plus a configurable timeout
   - `get`, `post`, `put` and `delete` helpers that return parsed JSON
   - a `User-Agent: activipyinfo/<version>` header
4. `exceptions.py`: `ActivityInfoError(status, code, message)` with subclasses `AuthenticationError` (401), `PermissionDeniedError` (403), `NotFoundError` (404), `ConflictError` (409), `DeletedError` (410), `RateLimitError` (429) and `ServerError` (5xx). The subclasses read the JSON error body.
5. `ids.cuid()`: an ID generator that follows the ActivityInfo CUID concept page (`/support/docs/api/concepts/cuids.html`).
6. Delete `constant.py`, `mixins/` and the `Manager` class, or keep `Manager` as a deprecated alias of `Client` for one release.
7. CI with GitHub Actions: ruff, mypy and pytest on Python 3.12 and 3.13.

### Phase 1: Account and databases

> **Status: done** on branch `phase-1-databases`.
> - The documented API has no way to rename a database or change its
>   description (`updateDatabase` only covers resources, locks, roles and
>   languages), so `update(label=..., description=...)` is **not**
>   implemented. See the open questions.
> - The original object API moved to `activipyinfo.legacy`, and `Manager` now
>   emits a `DeprecationWarning`.
> - Nested folders are sent with `parentId` set to a folder. The live test
>   `tests/integration/test_databases_live.py` checks that the server accepts
>   this; it needs `ACTIVITYINFO_ALLOW_WRITES=1`.
Endpoints: `GET /accounts/status`, `GET /databases`, `GET /databases/{id}` (tree), `POST /databases`, `POST /databases/{id}` (update), `DELETE /databases/{id}`, `GET /databases/{id}/billingAccount`.
1. `client.me()` returns a `UserAccount`.
2. Models: `Database` (id, label, description, owner, language, billing plan, role, `resources`, `roles`, `locks`) and `Resource` (id, type, parentId, label, visibility, icon).
3. `client.databases.list()`, `.get(id)`, `.create(label, description=None, template_id="")`, `.delete(id)` and `.update(id, label=..., description=...)`.
4. A `DatabaseChanges` builder for the `POST /databases/{id}` payload (resource, lock, role and language updates and deletions). Every folder, role and lock operation below goes through it, which replaces the hand-built dicts in `folder.py`.
5. Folders: `db.add_folder(label, parent=None)`, `folder.rename()`, `folder.move(parent)`, `folder.delete()`. **Check against the live API whether nested folders work** by setting `parentId` to a folder ID. The comment in `folder.py` says this is uncertain.
6. Navigating the tree: `db.folders`, `db.forms`, `db.find(label=...)`, `db.tree()` (printable), and lookup by label with a clear error when the label is ambiguous.

### Phase 2: Users, roles and permissions

> **Status: done** on branch `phase-2-users-roles`.
> - Payloads follow the R package, which is used against the live server,
>   wherever it disagrees with the API reference:
>   - A role's grant operations are sent as objects
>     (`{operation, filter, securityCategories}`, so formulas can restrict
>     records), with `optional` and `grantBased: true`.
>   - User role assignments are sent as `{id, parameters, resources}`.
>   - Parsing accepts both forms.
> - The per-user grants endpoint isn't used by R, so it follows the
>   documented shape (operations as strings). Record-level formulas can't
>   be sent through it.
> - `Role` ids are derived from labels when omitted (`"Data entry"` becomes
>   `"dataentry"`), and are validated like in R.
> - The tree's `role` and `grants` fields (the token user's own access) are
>   now `db.my_role` and `db.my_grants`. `db.roles` and `db.users` are
>   managers.
> - Deferred: `db.users.to_pandas()` (Phase 5, with the pandas extra) and
>   `db.users.sync()`.
Endpoints:
- `GET` and `POST /databases/{id}/users`
- `DELETE /databases/{id}/users/{userId}`
- `POST …/users/{userId}/role`
- `POST …/users/{userId}/grants`
- getting grants, and grants on a resource
- unlock and restore
- the billing account user, database and domain endpoints
1. Permission models modelled on the R `role()`, `grant()`, `databasePermissions()` and `resourcePermissions()`:
   - `Operation` enum. **Take the exact values from the `roleUpdates` / `permissions.operation` schema in `updateDatabase` before coding.**
   - `Permission(operation, filter=None, security_categories=())`
   - `RoleParameter`, `RoleFilter`, `Grant(resource, operations)`, `Role(id, label, permissions, parameters, filters, grants)`
2. `db.roles.list()`, `.get(id)`, `.add(role)`, `.update(role)`, `.delete(role)`. Each one sends a `roleUpdates` or `roleDeletions` payload through the `DatabaseChanges` builder.
3. `db.users.list()`, `.get(email_or_id)`, `.add(email, name, role, resources=None, parameters=None, grants=None, locale="en")`, `.remove(user)`, `.set_role(user, role, resources, parameters)`, `.update_grants(user, add=[...], remove=[...])`, `.unlock(user)` and `.restore(user)`.
4. `DatabaseUser` model covering activation, delivery and provisioning status, `locked` and last login.
5. Billing account (read-only at first): `client.billing.get(id)`, `.users(id)`, `.databases(id)` and `.domains(id)`.
6. Helpers: `db.users.to_pandas()`, and `db.users.sync(list_of_dicts)` for idempotent bulk onboarding. The sync helper can wait until later.

### Phase 3: Forms and schemas
Endpoints: `POST /databases/{id}/forms`, `GET` and `POST /form/{id}/schema`, schema version and diff, relocate, duplicate, recover a field, translations.
1. Typed field classes, one per API type, with shared attributes (`code`, `label`, `description`, `required`, `key`, `hidden`, `relevance`, `validation`, `required_condition`). Each class has `to_api()` / `from_api()`:
   - `TextField` (`FREE_TEXT`: input mask, barcode)
   - `MultilineField` (`NARRATIVE`)
   - `QuantityField` (units, aggregation)
   - `DateField`, `WeekField` (`epiweek`), `FortnightField`, `MonthField`
   - `SingleSelectField` / `MultiSelectField` (`enumerated` with cardinality, with options built from a list of labels)
   - `ReferenceField` (`reference`, which takes a `Form` or form ID)
   - `MultiSelectReferenceField`, `ReverseReferenceField`
   - `SubformField` (`subform`)
   - `CalculatedField` (`calculated`, formula)
   - `SerialNumberField` (`serial`)
   - `GeoPointField` (`geopoint`)
   - `AttachmentField` (`attachment`)
   - `SectionHeader` (`section`), `NoteField` (`note`)
   - `UnknownField` (keeps the raw JSON so reading and writing never loses data)
2. `FormSchema(label, fields, database_id, parent_form_id)` with `add_field`, `remove_field`, `get_field(code)`, `print()` / `to_pandas()` (like R `as.data.frame.formSchema`) and `to_api()`.
3. `folder.add_form(schema)` / `db.add_form(schema, parent=...)`, `form.schema()`, `form.update_schema(schema)` (handles `schemaVersion`), `form.add_field(field)`, `form.delete_field(code)`, `form.relocate(db_or_folder)`, `form.duplicate()`, `form.delete()`, and subforms.
4. `FormSchema.from_data(df_or_records)`, which infers fields the way R `createFormSchemaFromData` does. Nice to have.
5. Round-trip tests: fetch a real schema that uses every field type, save it as a fixture, and check that parsing it then serializing it gives back the same JSON.

### Phase 4: Records
Endpoints: `POST /resources/update` (at most 200 changes), `GET /form/{id}/record/{rid}`, record history, recover a deleted record.
1. `Record` model (`record_id`, `form_id`, `parent_record_id`, `last_edit_time`, `fields`).
2. `form.records.get(id)`, `.exists(id)`, `.add(values, record_id=None, parent=None)`, `.update(record_id, values)`, `.delete(record_id)`, `.history(record_id)` and `.recover(record_id)`.
3. `form.records.add_many(rows)` / `update_many` / `delete_many`. These split rows into batches of 200, report progress, and return the created IDs. Decide how partial failures are reported.
4. Converting values against the schema:
   - field codes to IDs (or rely on the API accepting codes, but validate the codes locally)
   - `date` / `datetime` to ISO strings
   - option labels to option IDs for select fields
   - `(lat, lon)` to a geopoint
   - references as record IDs, or via `ref_form.ref(**key_values)`, which looks up the ID with a filtered query instead of downloading the whole form. This fixes the current `add_record` / `update_record` bug.
5. A `client.records.batch()` context manager that queues changes across forms and submits them on exit. This is the equivalent of R `submitPending`.

### Phase 5: Queries and data frames
Endpoints: `POST /query/columns` (formId, columns[{id, formula}], filter, sort, filterSets), `POST /query/rows`, `GET /form/{id}/query`, pivot.
1. `client.queries.columns(form_id, columns, filter=None, sort=None)` turns the columnar response into a list of dicts.
2. `form.table()` returns a lazy `Table` modelled on R `getRecords() |> filter() |> select() |> collect()`:
   - `.select(*codes, **alias_formula)`
   - `.filter(formula)`
   - `.sort(col, desc=False)`
   - `.limit(n)` (like R `tblWindow`)
   - `.collect()` returns a list of dicts, `.to_pandas()` returns a DataFrame, and `__iter__` is supported
3. Default column selection follows the R "pretty columns" style: field labels, referenced key fields expanded, and `_id` / `_lastEditTime` optional.
4. A small formula helper for quoting and `==`, `&&` and `ISBLANK` (a basic version of `toActivityInfoFormula`). Keep it simple, because formulas are passed through as strings.
5. `form.to_pandas()` as a one-line shortcut.

### Phase 6: Jobs and bulk operations
Endpoints: `POST /jobs`, `GET /jobs/{id}`, the job file endpoint, and descriptors `importRecords`, `exportForm`, `exportDatabaseForms`, `importXlsForm`, `duplicateDatabase`, `exportAuditLog`, `exportUsers`, `mergeRecords`, `exportAttachments`.
1. `client.jobs.start(type, descriptor)` returns a `Job`, with `job.wait(poll=2, timeout=...)`, `job.download(path)` and `job.result`. A failed job raises `JobFailedError` with the API error.
2. `form.import_records(df_or_csv)` uses the staged import (`stageImport` then an `importRecords` job). **Find the staging endpoint first.** It isn't in the API index, but the R `stageImport` source shows the call. Fall back to `add_many` for small inputs.
3. `form.export(format="csv"|"xlsx", path=...)`, `db.export_forms(...)`, `db.duplicate(label)`, `client.import_xlsform(path, db, folder)` and `db.audit_log(...)`, which returns a DataFrame like R `queryAuditLog`.

### Phase 7: Remaining areas (lower priority)
- Attachments: upload, status and download (`record.download_attachment(field, path)`).
- Locks: `db.locks.add(label, resource, date_range | formula)` through `lockUpdates`.
- Translations: database and form translations, and adding or removing languages.
- Reports: list, get, and results or rows as a DataFrame (R `queryReportResults`).
- Search, ping, icons, form GeoJSON (`form.geojson()`) and schema history or diff.
- OAuth support: a `Client(oauth_token=..., refresh=callable)` refresh hook.

### Phase 8: Documentation and release
1. Rewrite the README around the new API (quickstart, authentication, examples) and turn the old README scenarios (Admin1 / Admin2 with a reference) into an integration test.
2. An MkDocs Material site with an API reference generated by `mkdocstrings`, a "Coming from R" page that maps each R function to its Python equivalent, and recipes (bulk import, user onboarding, exporting to pandas).
3. Semantic versioning. Release `0.2.0` after phases 0 to 2, `0.3.0` after phases 3 and 4, and `1.0.0` once the API is stable. Publish to PyPI using Trusted Publishing in GitHub Actions.

---

## 4. Suggested order of the first pull requests
1. Phase 0: `Client`, `exceptions` and packaging. Adapt the existing tests.
2. Phase 1: databases and folders, including the `DatabaseChanges` builder.
3. Phase 2a: roles and permission models, then `db.roles`.
4. Phase 2b: `db.users` and billing reads.
5. Phase 3a: field classes and the `FormSchema` round-trip.
6. Phase 3b: form operations (add, update schema, delete, relocate).
7. Phase 4: records CRUD, batching and value conversion (this fixes the reference bug).
8. Phase 5: `Table` query builder and pandas.
9. Phase 6: the job runner, import and export.

## 5. Open questions to settle against the live API
- Role grants and user roles: the R package and the API reference disagree on the payload shape (objects vs strings, `id` vs `roleId`). `tests/integration/test_users_roles_live.py` checks the R format.
- Per-user grants (`POST …/users/{id}/grants`): are operations strings or permission objects?
- How to rename a database or change its description (the web app does it, but the endpoint isn't documented).
- Whether nested folders can be created through `resourceUpdates`.
- The staging endpoint behind R `stageImport`.
- Whether `/resources/update` accepts field **codes** for every field type (the documentation says "IDs or codes").
- The exact response shape of `/query/columns`. Save it as a fixture.
- How to give a subform record its `parentRecordId`, and how to create subform schemas.
