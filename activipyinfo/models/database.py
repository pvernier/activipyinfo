from __future__ import annotations

import builtins
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self, TypeVar, overload

from ..exceptions import ConfigurationError, NoMatchError, NotFoundError
from ..ids import cuid
from ._common import one
from .changes import DatabaseChanges
from .fields import FormField, SubformField
from .form_schema import FormSchema
from .permissions import Grant, Role, RoleAssignment

if TYPE_CHECKING:
    from ..client import Client
    from .account import BillingAccount
    from .audit import AuditEvent
    from .form_records import FormRecords
    from .job import Job
    from .table import ColumnNames, Table
    from .user import DatabaseUser

__all__ = [
    "Database",
    "DatabaseRoles",
    "DatabaseUsers",
    "Folder",
    "Form",
    "OwnerRef",
    "Report",
    "Resource",
    "ResourceType",
    "SubForm",
    "Visibility",
]


class ResourceType(StrEnum):
    DATABASE = "DATABASE"
    FOLDER = "FOLDER"
    FORM = "FORM"
    SUB_FORM = "SUB_FORM"
    REPORT = "REPORT"


class Visibility(StrEnum):
    PRIVATE = "PRIVATE"
    PUBLIC = "PUBLIC"
    REFERENCE = "REFERENCE"


@dataclass
class OwnerRef:
    id: str
    name: str | None = None
    email: str | None = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> OwnerRef:
        return cls(id=str(data["id"]), name=data.get("name"), email=data.get("email"))


R = TypeVar("R", bound="Resource")


# ----------------------------------------------------------------------
# Resources: the folders, forms, subforms and reports of a database
# ----------------------------------------------------------------------


@dataclass(eq=False)
class Resource:
    """A node of a database tree (folder, form, subform or report).

    Resources are obtained from a :class:`Database` (``db.resources``,
    ``db.find(...)``) and stay attached to it: renaming, moving or deleting
    a resource updates the database on the server and refreshes ``db``.
    """

    id: str
    label: str
    type: str
    parent_id: str | None = None
    visibility: str | None = None
    icon: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    _database: Database | None = field(default=None, init=False, repr=False)

    @classmethod
    def from_api(
        cls, data: dict[str, Any], database: Database | None = None
    ) -> Resource:
        """Build the right subclass (Folder, Form, ...) from a tree entry."""
        resource_type = data.get("type", "")
        klass = _RESOURCE_CLASSES.get(resource_type, cls)
        resource = klass(
            id=data["id"],
            label=data.get("label", ""),
            type=resource_type,
            parent_id=data.get("parentId"),
            visibility=data.get("visibility"),
            icon=data.get("icon"),
            raw=data,
        )
        resource._database = database
        return resource

    def to_api(self) -> dict[str, Any]:
        """Serialize as a ``resourceUpdates`` entry."""
        data: dict[str, Any] = {
            "id": self.id,
            "parentId": self.parent_id,
            "label": self.label,
            "type": str(self.type),
            "visibility": str(self.visibility or Visibility.PRIVATE),
        }
        if self.icon:
            data["icon"] = self.icon
        return data

    def __repr__(self) -> str:
        return f"{type(self).__name__}(id={self.id!r}, label={self.label!r})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Resource) and other.id == self.id

    def __hash__(self) -> int:
        return hash(self.id)

    @property
    def database(self) -> Database:
        if self._database is None:
            raise ConfigurationError(f"{self!r} is not attached to a Database.")
        return self._database

    @property
    def parent(self) -> Resource | Database:
        """The folder containing this resource, or the database itself."""
        db = self.database
        for resource in db.resources:
            if resource.id == self.parent_id:
                return resource
        return db

    @property
    def path(self) -> list[str]:
        """Labels from the database root down to this resource."""
        labels = [self.label]
        parent = self.parent
        while isinstance(parent, Resource):
            labels.append(parent.label)
            parent = parent.parent
        return list(reversed(labels))

    @property
    def children(self) -> list[Resource]:
        return [r for r in self.database.resources if r.parent_id == self.id]

    def rename(self, label: str) -> Self:
        """Change the label of this resource on the server."""
        changes = DatabaseChanges()
        changes.update_resource({**self.to_api(), "label": label})
        self.database.apply(changes)
        self.label = label
        return self

    def move(self, parent: Folder | Database | str) -> Self:
        """Move this resource into another folder (or to the database root)."""
        parent_id = self.database._parent_id(parent)
        changes = DatabaseChanges()
        changes.update_resource({**self.to_api(), "parentId": parent_id})
        self.database.apply(changes)
        self.parent_id = parent_id
        return self

    def delete(self) -> None:
        """Delete this resource and everything it contains."""
        changes = DatabaseChanges()
        changes.delete_resource(self.id)
        self.database.apply(changes)


class Folder(Resource):
    """A folder of a database."""

    @property
    def folders(self) -> list[Folder]:
        return [r for r in self.children if isinstance(r, Folder)]

    @property
    def forms(self) -> list[Form]:
        return [r for r in self.children if type(r) is Form]

    def add_folder(self, label: str, *, id: str | None = None) -> Folder:
        """Create a sub-folder."""
        return self.database.add_folder(label, parent=self, id=id)

    def add_form(
        self, schema: FormSchema | str, fields: list[FormField] | None = None
    ) -> Form:
        """Create a form in this folder. See :meth:`Database.add_form`."""
        return self.database.add_form(schema, fields, parent=self)


class Form(Resource):
    """A form of a database: its schema and its records."""

    @cached_property
    def records(self) -> FormRecords:
        """Read, add, update and delete this form's records."""
        from .form_records import FormRecords

        return FormRecords(self)

    def table(self, names: ColumnNames = "label") -> Table:
        """A lazy query over this form's records; see :class:`Table`.

        ``names`` sets the default column names: field ``"label"`` (like the
        R package's pretty columns), ``"code"`` or ``"id"``.
        """
        from .table import Table

        return Table(self, names=names)

    def to_pandas(self, names: ColumnNames = "label") -> Any:
        """All records as a :class:`pandas.DataFrame` (needs pandas)."""
        return self.table(names).to_pandas()

    def export(
        self,
        file_format: str = "CSV",
        destination: str | Path | None = None,
        *,
        names: ColumnNames = "label",
        timeout: float | None = None,
    ) -> Path:
        """Export all records to a file on the server and download it.

        See :meth:`Table.export` to export chosen columns or records.
        """
        return self.table(names).export(file_format, destination, timeout=timeout)

    @property
    def _forms(self) -> Any:
        return self.database.client.forms

    def schema(self) -> FormSchema:
        """Fetch the form's current schema."""
        schema: FormSchema = self._forms.get_schema(self.id)
        return schema

    def update_schema(self, schema: FormSchema) -> FormSchema:
        """Replace the form's schema; fields are matched by id.

        Typical use: ``s = form.schema()``, edit ``s``, then
        ``form.update_schema(s)``. A field missing from ``schema`` is deleted
        (with its data, which :meth:`recover_field` can restore).
        """
        if schema.id != self.id:
            raise ValueError(f"Schema {schema.id!r} is not the schema of {self!r}")
        updated: FormSchema = self._forms.update_schema(schema)
        if updated.label != self.label:
            self.database.refresh()
        return updated

    def add_field(
        self, new_field: FormField, *, after: FormField | str | None = None
    ) -> FormField:
        """Add a field at the end of the form, or after another field."""
        schema = self.schema()
        schema.add_field(new_field, after=after)
        return self.update_schema(schema).field(new_field.id)

    def delete_field(self, key: FormField | str) -> FormField:
        """Delete a field (by object, id, code or label) and return it."""
        schema = self.schema()
        removed = schema.remove_field(
            key if isinstance(key, str) else schema.field(key.id)
        )
        self.update_schema(schema)
        return removed

    def recover_field(self, field_id: str) -> FormSchema:
        """Restore a deleted field, with its data."""
        schema: FormSchema = self._forms.recover_field(self.id, field_id)
        return schema

    def schema_version(self, version: int) -> FormSchema:
        """Fetch an earlier version of the schema."""
        schema: FormSchema = self._forms.schema_version(self.id, version)
        return schema

    def add_subform(
        self, schema: FormSchema | str, fields: list[FormField] | None = None
    ) -> SubForm:
        """Create a subform (repeating records) linked from this form.

        The server requires the parent form to reference the subform first:
        a :class:`SubformField` is added to this form's schema, then the
        subform's schema is saved. If saving the subform fails, the new
        field is removed from this form again.
        """
        subform_schema = _as_schema(schema, fields)
        subform_schema.database_id = self.database.id
        subform_schema.parent_form_id = self.id

        parent_schema = self.schema()
        new_link: SubformField | None = None
        if not any(
            f.subform_id == subform_schema.id for f in parent_schema.subform_fields
        ):
            new_link = SubformField(subform_schema.label, subform_schema.id)
            parent_schema.add_field(new_link)
            self.update_schema(parent_schema)

        try:
            try:
                self._forms.update_schema(subform_schema)
            except NotFoundError:
                # The server did not create the subform from the new field.
                self._forms.add(subform_schema)
        except Exception:
            if new_link is not None:
                rollback = self.schema()
                links = [
                    f
                    for f in rollback.subform_fields
                    if f.subform_id == subform_schema.id
                ]
                for link in links:
                    rollback.remove_field(link)
                if links:
                    self.update_schema(rollback)
            raise

        self.database.refresh()
        subform = self.database.resource(subform_schema.id)
        assert isinstance(subform, SubForm)
        return subform

    def relocate(self, database: Database | str) -> None:
        """Move this form, with its subforms and records, to another database."""
        database_id = database if isinstance(database, str) else database.id
        self._forms.relocate(self.id, database_id)
        self.database.refresh()

    def duplicate(self) -> Form:
        """Copy this form's structure (not its records) in the same database."""
        db = self.database
        before = {r.id for r in db.resources}
        updated = self._forms.duplicate(db.id, self.id)
        db._load(updated.raw)
        if db._resources is None:
            db.refresh()
        copy = one(
            (r for r in db.forms if r.id not in before),
            f"copy of {self!r}",
        )
        return copy


class SubForm(Form):
    """A subform (repeating section) of a form."""


class Report(Resource):
    """A report of a database."""


_RESOURCE_CLASSES: dict[str, type[Resource]] = {
    ResourceType.FOLDER: Folder,
    ResourceType.FORM: Form,
    ResourceType.SUB_FORM: SubForm,
    ResourceType.REPORT: Report,
}


# ----------------------------------------------------------------------
# Database
# ----------------------------------------------------------------------


@dataclass(eq=False)
class Database:
    """An ActivityInfo database.

    Databases returned by ``client.databases.list()`` only carry summary
    fields; the full tree (resources, roles, locks, ...) is fetched the first
    time it is needed, or explicitly with :meth:`refresh`.
    """

    id: str
    label: str
    description: str | None = None
    owner_id: str | None = None
    owner: OwnerRef | None = None
    billing_account_id: int | None = None
    billing_plan: str | None = None
    suspended: bool = False
    published_template: bool = False
    version: Any = None
    language: str | None = None
    original_language: str | None = None
    languages: list[str] = field(default_factory=list)
    # The token user's own role and grants in this database.
    my_role: RoleAssignment | None = field(default=None, repr=False)
    my_grants: list[Grant] = field(default_factory=list, repr=False)
    # Typed in phase 7.
    locks: list[dict[str, Any]] = field(default_factory=list, repr=False)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    _client: Client | None = field(default=None, init=False, repr=False)
    _resources: list[Resource] | None = field(default=None, init=False, repr=False)
    _roles: list[Role] = field(default_factory=list, init=False, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any], client: Client | None = None) -> Database:
        """Parse a database summary (``GET /databases``) or tree."""
        db = cls(id=data["databaseId"], label=data.get("label", ""))
        db._client = client
        db._load(data)
        return db

    def _load(self, data: dict[str, Any]) -> None:
        owner = data.get("ownerRef")
        self.id = data["databaseId"]
        self.label = data.get("label", self.label)
        self.description = data.get("description") or None
        self.owner = OwnerRef.from_api(owner) if owner else None
        self.owner_id = self.owner.id if self.owner else data.get("ownerId")
        self.billing_account_id = data.get("billingAccountId")
        self.billing_plan = data.get("billingPlan")
        self.suspended = data.get("suspended", False)
        self.published_template = data.get("publishedTemplate", False)
        self.version = data.get("version")
        self.language = data.get("language")
        self.original_language = data.get("originalLanguage")
        self.languages = list(data.get("languages") or [])
        role = data.get("role")
        self.my_role = RoleAssignment.from_api(role) if role else None
        self.my_grants = [Grant.from_api(g) for g in data.get("grants") or []]
        self._roles = [Role.from_api(r) for r in data.get("roles") or []]
        self.locks = list(data.get("locks") or [])
        self.raw = data
        if "resources" in data:
            self._resources = [
                Resource.from_api(item, database=self) for item in data["resources"]
            ]

    def __repr__(self) -> str:
        return f"Database(id={self.id!r}, label={self.label!r})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Database) and other.id == self.id

    def __hash__(self) -> int:
        return hash(self.id)

    @property
    def client(self) -> Client:
        if self._client is None:
            raise ConfigurationError(f"{self!r} is not attached to a Client.")
        return self._client

    # -- Loading ---------------------------------------------------------

    def refresh(self) -> Self:
        """Reload the full database tree from the server."""
        self._load(self.client.databases.get(self.id).raw)
        return self

    def apply(self, changes: DatabaseChanges) -> Self:
        """Apply a batch of changes and refresh this database from the result."""
        updated = self.client.databases.update(self.id, changes)
        self._load(updated.raw)
        return self

    # -- Resources -------------------------------------------------------

    def _ensure_tree(self) -> None:
        if self._resources is None:
            self.refresh()

    @property
    def resources(self) -> list[Resource]:
        """All folders, forms, subforms and reports (loads the tree if needed)."""
        self._ensure_tree()
        assert self._resources is not None
        return self._resources

    # -- Roles and users -------------------------------------------------

    @property
    def roles(self) -> DatabaseRoles:
        """The roles defined in this database; also adds, updates and deletes them."""
        return DatabaseRoles(self)

    @property
    def users(self) -> DatabaseUsers:
        """Lists, invites and manages the users of this database."""
        return DatabaseUsers(self)

    @property
    def folders(self) -> list[Folder]:
        return [r for r in self.resources if isinstance(r, Folder)]

    @property
    def forms(self) -> list[Form]:
        """All forms, excluding subforms."""
        return [r for r in self.resources if type(r) is Form]

    @property
    def children(self) -> list[Resource]:
        """Resources at the root of the database."""
        ids = {r.id for r in self.resources}
        return [
            r
            for r in self.resources
            if r.parent_id is None or r.parent_id == self.id or r.parent_id not in ids
        ]

    def resource(self, resource_id: str) -> Resource:
        """Return the resource with the given id."""
        return one(
            (r for r in self.resources if r.id == resource_id),
            f"resource with id {resource_id!r} in {self!r}",
        )

    def find_all(
        self,
        label: str | None = None,
        *,
        type: str | type[R] | None = None,
        parent: Folder | Database | str | None = None,
    ) -> list[Resource]:
        """Return the resources matching every given criterion.

        Args:
            label: Exact label (case-sensitive).
            type: A :class:`ResourceType` / type string (``"FORM"``) or a
                resource class (``Folder``, ``Form``, ...).
            parent: Only direct children of this folder (or of the database).
        """
        matches = list(self.resources)
        if label is not None:
            matches = [r for r in matches if r.label == label]
        if isinstance(type, str):
            matches = [r for r in matches if r.type == type]
        elif type is not None:
            klass = type
            matches = [r for r in matches if isinstance(r, klass)]
        if parent is not None:
            parent_id = self._parent_id(parent)
            roots = set(self.children) if parent_id == self.id else set()
            matches = [r for r in matches if r.parent_id == parent_id or r in roots]
        return matches

    def find(
        self,
        label: str,
        *,
        type: str | type[R] | None = None,
        parent: Folder | Database | str | None = None,
    ) -> Resource:
        """Return the single resource with this label.

        Raises:
            NoMatchError: nothing matches.
            MultipleMatchesError: several resources match; narrow the search
                with ``type=`` or ``parent=``, or use :meth:`resource` with an id.
        """
        return one(
            self.find_all(label, type=type, parent=parent),
            f"resource labelled {label!r} in {self!r}",
        )

    def folder(self, label_or_id: str) -> Folder:
        """Return a folder by id or by (unique) label."""
        return self._lookup(label_or_id, Folder)

    def form(self, label_or_id: str) -> Form:
        """Return a form or subform by id or by (unique) label."""
        return self._lookup(label_or_id, Form)

    def _lookup(self, label_or_id: str, klass: type[R]) -> R:
        for r in self.resources:
            if r.id == label_or_id and isinstance(r, klass):
                return r
        found = self.find(label_or_id, type=klass)
        assert isinstance(found, klass)
        return found

    def _parent_id(self, parent: Resource | Database | str | None) -> str:
        if parent is None:
            return self.id
        if isinstance(parent, str):
            return parent
        if isinstance(parent, Resource) and parent._database not in (None, self):
            raise ValueError(f"{parent!r} belongs to another database")
        return parent.id

    def tree(self) -> str:
        """Return a printable outline of the database's folders and forms."""
        lines = [f"{self.label} ({self.id})"]

        def walk(nodes: list[Resource], prefix: str) -> None:
            for index, node in enumerate(nodes):
                last = index == len(nodes) - 1
                kind = str(node.type).lower().replace("_", "")
                lines.append(
                    f"{prefix}{'└── ' if last else '├── '}{node.label} "
                    f"[{kind} {node.id}]"
                )
                walk(node.children, prefix + ("    " if last else "│   "))

        walk(self.children, "")
        return "\n".join(lines)

    # -- Changes ---------------------------------------------------------

    def add_folder(
        self,
        label: str,
        parent: Folder | Database | str | None = None,
        *,
        id: str | None = None,
    ) -> Folder:
        """Create a folder at the root of the database or inside ``parent``."""
        folder_id = id or cuid()
        changes = DatabaseChanges()
        changes.update_resource(
            {
                "id": folder_id,
                "parentId": self._parent_id(parent),
                "label": label,
                "type": str(ResourceType.FOLDER),
                "visibility": str(Visibility.PRIVATE),
            }
        )
        self.apply(changes)
        folder = self.resource(folder_id)
        assert isinstance(folder, Folder)
        return folder

    def add_form(
        self,
        schema: FormSchema | str,
        fields: list[FormField] | None = None,
        *,
        parent: Folder | Database | str | None = None,
    ) -> Form:
        """Create a form.

        Args:
            schema: A :class:`FormSchema`, or just the new form's label.
            fields: The fields, when ``schema`` is a label.
            parent: Folder that will contain the form (default: the root).

        Example:
            >>> db.add_form("Households", [TextField("Head", key=True)])
        """
        form_schema = _as_schema(schema, fields)
        form_schema.database_id = self.id
        parent_id = self._parent_id(parent)
        self.client.forms.add(form_schema, parent_id=parent_id)
        self.refresh()
        return self.form(form_schema.id)

    def export(
        self,
        file_format: str = "XLSX",
        destination: str | Path | None = None,
        *,
        folder: Resource | str | None = None,
        layout: str = "WIDE",
        filter: str | None = None,
        include_blanks: bool = False,
        timeout: float | None = None,
        progress: Callable[[Job], None] | None = None,
    ) -> Path:
        """Export the records of all forms (or of one folder or form).

        Args:
            file_format: ``"XLSX"``, ``"CSV"``, ``"NDJSON"``, ``"SQLITE"``...
            destination: File path or directory (default: current directory).
            folder: Only export this folder or form.
            layout: ``"WIDE"`` (one column per field) or ``"LONG"``.
            filter: A formula applied to every form.
            include_blanks: Include rows for blank quantities (long layout).
        """
        from ..services.jobs import utc_offset_minutes

        descriptor: dict[str, Any] = {
            "databaseId": self.id,
            "format": layout.upper(),
            "fileFormat": file_format.upper(),
            "includeBlanks": include_blanks,
            "utcOffset": utc_offset_minutes(),
        }
        if folder is not None:
            descriptor["folderId"] = folder if isinstance(folder, str) else folder.id
        if filter:
            descriptor["filter"] = filter
        job = self.client.jobs.run(
            "exportDatabaseForms", descriptor, timeout=timeout, progress=progress
        )
        return job.download(destination)

    def duplicate(
        self,
        label: str,
        *,
        records: bool = False,
        timeout: float | None = None,
        progress: Callable[[Job], None] | None = None,
    ) -> Database:
        """Copy this database (forms, folders, roles; optionally its records)
        into a new database."""
        return self.client.databases.duplicate(
            self.id, label, records=records, timeout=timeout, progress=progress
        )

    def import_xlsform(
        self,
        xlsform: str | Path | bytes,
        parent: Folder | Database | str | None = None,
        *,
        timeout: float | None = None,
    ) -> Form:
        """Create a form from an XLSForm (``.xlsx`` path or bytes)."""
        content = xlsform if isinstance(xlsform, bytes) else Path(xlsform).read_bytes()
        import_id = self.client.jobs.stage(
            content,
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )
        job = self.client.jobs.run(
            "importXlsform",
            {
                "databaseId": self.id,
                "parentId": self._parent_id(parent),
                "importId": import_id,
            },
            timeout=timeout,
        )
        self.refresh()
        return self.form(job.result["formId"])

    def audit_log(
        self,
        *,
        before: datetime | None = None,
        after: datetime | None = None,
        resource: Resource | str | None = None,
        types: Sequence[str] | None = None,
        limit: int = 1000,
    ) -> list[AuditEvent]:
        """Audit log events, most recent first; see
        :meth:`activipyinfo.services.DatabasesService.audit_log`."""
        resource_id = resource.id if isinstance(resource, Resource) else resource
        return self.client.databases.audit_log(
            self.id,
            before=before,
            after=after,
            resource_id=resource_id,
            types=types,
            limit=limit,
        )

    def delete(self) -> None:
        """Delete the database. Only its owner can do this."""
        self.client.databases.delete(self.id)

    def billing_account(self) -> BillingAccount:
        """Return the billing account that owns this database."""
        return self.client.databases.billing_account(self.id)


def _as_schema(schema: FormSchema | str, fields: list[FormField] | None) -> FormSchema:
    if isinstance(schema, FormSchema):
        if fields:
            raise ValueError("Pass the fields in the FormSchema, not separately")
        return schema
    return FormSchema(schema, fields or [])


# ----------------------------------------------------------------------
# Roles and users of a database
# ----------------------------------------------------------------------


class DatabaseRoles(Sequence[Role]):
    """The roles of a database, as returned by ``db.roles``.

    Behaves like a read-only list of :class:`Role` (loaded with the database
    tree) and adds :meth:`get`, :meth:`add`, :meth:`update` and :meth:`delete`.
    """

    def __init__(self, database: Database) -> None:
        self._db = database

    def _list(self) -> list[Role]:
        self._db._ensure_tree()
        return self._db._roles

    @overload
    def __getitem__(self, index: int) -> Role: ...
    @overload
    def __getitem__(self, index: slice) -> Sequence[Role]: ...
    def __getitem__(self, index: int | slice) -> Role | Sequence[Role]:
        return self._list()[index]

    def __len__(self) -> int:
        return len(self._list())

    def __iter__(self) -> Iterator[Role]:
        return iter(self._list())

    def __repr__(self) -> str:
        return f"DatabaseRoles({[r.id for r in self._list()]!r})"

    def get(self, id_or_label: str) -> Role:
        """Return a role by id, or by (unique) label."""
        roles = self._list()
        for role in roles:
            if role.id == id_or_label:
                return role
        return one(
            (r for r in roles if r.label == id_or_label),
            f"role {id_or_label!r} in {self._db!r}",
        )

    def add(self, role: Role) -> Role:
        """Create a role. Raises ValueError if a role with the same id exists."""
        if any(r.id == role.id for r in self._list()):
            raise ValueError(
                f"Role {role.id!r} already exists in {self._db!r}; use update()."
            )
        return self.update(role)

    def update(self, role: Role) -> Role:
        """Create or replace a role (matched by id)."""
        changes = DatabaseChanges()
        changes.update_role(role)
        self._db.apply(changes)
        return self.get(role.id)

    def delete(self, role: Role | str) -> None:
        """Delete a role by object, id or label."""
        role_id = role.id if isinstance(role, Role) else self.get(role).id
        changes = DatabaseChanges()
        changes.delete_role(role_id)
        self._db.apply(changes)


class DatabaseUsers:
    """The users of a database, as returned by ``db.users``.

    Users can be referred to by :class:`DatabaseUser`, user id or email.
    Roles can be referred to by :class:`Role`, id or label.
    """

    def __init__(self, database: Database) -> None:
        self._db = database

    def __repr__(self) -> str:
        return f"DatabaseUsers({self._db!r})"

    def _user_id(self, user: DatabaseUser | str) -> str:
        if not isinstance(user, str):
            return user.user_id
        if "@" not in user:
            return user
        email = user.lower()
        return one(
            (u for u in self.list() if u.email.lower() == email),
            f"user with email {user!r} in {self._db!r}",
        ).user_id

    def _role(self, role: Role | str) -> Role | str:
        if isinstance(role, Role):
            return role
        try:
            return self._db.roles.get(role)
        except NoMatchError:
            return role  # e.g. a role id not listed in the tree

    def list(self) -> builtins.list[DatabaseUser]:
        """List the users of the database."""
        return self._db.client.users.list(self._db.id)

    def get(self, user: str) -> DatabaseUser:
        """Fetch a user, with their grants, by id or email."""
        return self._db.client.users.get(self._db.id, self._user_id(user))

    def on_resource(self, resource: Resource | str) -> builtins.list[DatabaseUser]:
        """List the users with access to a folder or form."""
        resource_id = resource if isinstance(resource, str) else resource.id
        return self._db.client.users.on_resource(self._db.id, resource_id)

    def add(
        self,
        email: str,
        name: str,
        role: Role | str,
        *,
        resources: builtins.list[Any] | None = None,
        parameters: dict[str, str] | None = None,
        locale: str = "en",
    ) -> DatabaseUser:
        """Invite a user. See :meth:`activipyinfo.services.UsersService.add`."""
        return self._db.client.users.add(
            self._db.id,
            email,
            name,
            self._role(role),
            resources=resources,
            parameters=parameters,
            locale=locale,
        )

    def set_role(
        self,
        user: DatabaseUser | str,
        role: Role | str,
        *,
        resources: builtins.list[Any] | None = None,
        parameters: dict[str, str] | None = None,
    ) -> DatabaseUser:
        """Replace a user's role assignment."""
        return self._db.client.users.set_role(
            self._db.id,
            self._user_id(user),
            self._role(role),
            resources=resources,
            parameters=parameters,
        )

    def update_grants(
        self,
        user: DatabaseUser | str,
        *,
        add: builtins.list[Grant] | None = None,
        remove: builtins.list[Any] | None = None,
    ) -> DatabaseUser:
        """Grant or revoke permissions on specific resources, outside the role."""
        return self._db.client.users.update_grants(
            self._db.id, self._user_id(user), add=add, remove=remove
        )

    def remove(self, user: DatabaseUser | str) -> None:
        """Remove a user from the database."""
        self._db.client.users.remove(self._db.id, self._user_id(user))

    def unlock(self, user: DatabaseUser | str) -> None:
        """Unlock a user's account in the database."""
        self._db.client.users.unlock(self._db.id, self._user_id(user))

    def restore(self, user_id: str) -> DatabaseUser:
        """Restore a removed user (by id) with their former role and grants."""
        return self._db.client.users.restore(self._db.id, user_id)

    def to_pandas(self) -> Any:
        """The users of the database as a :class:`pandas.DataFrame`."""
        from .._pandas import require_pandas

        pd = require_pandas()
        return pd.DataFrame(
            [
                {
                    "user_id": u.user_id,
                    "email": u.email,
                    "name": u.name,
                    "role_id": u.role.role_id if u.role else None,
                    "role_resources": u.role.resources if u.role else [],
                    "role_parameters": u.role.parameters if u.role else {},
                    "activation_status": u.activation_status,
                    "user_license_type": u.user_license_type,
                    "last_login_time": u.last_login_time,
                    "locked": u.locked,
                }
                for u in self.list()
            ]
        )
