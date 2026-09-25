from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Self, TypeVar

from ..exceptions import ConfigurationError
from ..ids import cuid
from ._common import one
from .changes import DatabaseChanges

if TYPE_CHECKING:
    from ..client import Client
    from .account import BillingAccount

__all__ = [
    "Database",
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


class Form(Resource):
    """A form of a database. Schema and records support comes in later phases."""


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
    # Typed in phase 2 (users, roles and permissions).
    role: dict[str, Any] | None = field(default=None, repr=False)
    roles: list[dict[str, Any]] = field(default_factory=list, repr=False)
    locks: list[dict[str, Any]] = field(default_factory=list, repr=False)
    grants: list[dict[str, Any]] = field(default_factory=list, repr=False)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    _client: Client | None = field(default=None, init=False, repr=False)
    _resources: list[Resource] | None = field(default=None, init=False, repr=False)

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
        self.role = data.get("role")
        self.roles = list(data.get("roles") or [])
        self.locks = list(data.get("locks") or [])
        self.grants = list(data.get("grants") or [])
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

    @property
    def resources(self) -> list[Resource]:
        """All folders, forms, subforms and reports (loads the tree if needed)."""
        if self._resources is None:
            self.refresh()
        assert self._resources is not None
        return self._resources

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

    def delete(self) -> None:
        """Delete the database. Only its owner can do this."""
        self.client.databases.delete(self.id)

    def billing_account(self) -> BillingAccount:
        """Return the billing account that owns this database."""
        return self.client.databases.billing_account(self.id)
