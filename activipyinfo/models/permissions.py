"""Roles, permissions and grants.

Modelled on the R package's ``role()``, ``grant()``, ``resourcePermissions()``,
``databasePermissions()``, ``parameter()`` and ``roleAssignment()``, and
serialized the way it does: a role's grants carry a list of permission
objects, so each operation can be restricted by a formula (record-level
permission).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from ..ids import cuid

__all__ = [
    "Grant",
    "Operation",
    "Permission",
    "Role",
    "RoleAssignment",
    "RoleParameter",
    "database_permissions",
    "resource_permissions",
]

_ROLE_ID = re.compile(r"^[a-z][a-z0-9]{0,31}$")
_PARAMETER_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")


class Operation(StrEnum):
    """An operation a role or grant can allow."""

    VIEW = "VIEW"
    DISCOVER = "DISCOVER"
    ADD_RECORD = "ADD_RECORD"
    EDIT_RECORD = "EDIT_RECORD"
    DELETE_RECORD = "DELETE_RECORD"
    BULK_DELETE = "BULK_DELETE"
    EXPORT_RECORDS = "EXPORT_RECORDS"
    LOCK_RECORDS = "LOCK_RECORDS"
    MANAGE_REFERENCE_DATA = "MANAGE_REFERENCE_DATA"
    MANAGE_USERS = "MANAGE_USERS"
    MANAGE_ROLES = "MANAGE_ROLES"
    ADD_RESOURCE = "ADD_RESOURCE"
    EDIT_RESOURCE = "EDIT_RESOURCE"
    DELETE_RESOURCE = "DELETE_RESOURCE"
    MANAGE_COLLECTION_LINKS = "MANAGE_COLLECTION_LINKS"
    AUDIT = "AUDIT"
    SHARE_REPORTS = "SHARE_REPORTS"
    PUBLISH_REPORTS = "PUBLISH_REPORTS"
    MANAGE_AUTOMATIONS = "MANAGE_AUTOMATIONS"
    MANAGE_TRANSLATIONS = "MANAGE_TRANSLATIONS"
    RESOLVE_DUPLICATES = "RESOLVE_DUPLICATES"
    SHARE_VIEWS = "SHARE_VIEWS"
    MANAGE_IMPORT_CONFIGS = "MANAGE_IMPORT_CONFIGS"
    VIEW_FIELD = "VIEW_FIELD"
    EDIT_FIELD = "EDIT_FIELD"


def _operation(value: str) -> Operation | str:
    # Unknown operations (added to the API later) are kept as plain strings.
    try:
        return Operation(value)
    except ValueError:
        return value


def _id_of(value: Any) -> str:
    return value if isinstance(value, str) else value.id


@dataclass(frozen=True)
class Permission:
    """One allowed operation, optionally restricted to records matching a formula.

    Example:
        >>> Permission(Operation.EDIT_RECORD, filter="[partner] == @user.partner")
    """

    operation: Operation | str
    filter: str | None = None
    security_categories: tuple[str, ...] = ()

    @classmethod
    def from_api(cls, data: str | dict[str, Any]) -> Permission:
        if isinstance(data, str):
            return cls(_operation(data))
        return cls(
            operation=_operation(data["operation"]),
            filter=data.get("filter") or None,
            security_categories=tuple(data.get("securityCategories") or ()),
        )

    def to_api(self) -> dict[str, Any]:
        data: dict[str, Any] = {"operation": str(self.operation)}
        if self.filter:
            data["filter"] = self.filter
        data["securityCategories"] = list(self.security_categories)
        return data


def _permissions(
    values: dict[str, bool | str], reviewer_only: bool = False
) -> list[Permission]:
    permissions = []
    for name, value in values.items():
        if value is False or value is None:
            continue
        if not isinstance(value, bool | str):
            raise TypeError(f"{name} must be a bool or a formula string")
        operation = Operation(name.upper())
        categories: tuple[str, ...] = ()
        if reviewer_only and operation in (Operation.ADD_RECORD, Operation.EDIT_RECORD):
            categories = ("reviewer",)
        permissions.append(
            Permission(
                operation,
                filter=value if isinstance(value, str) else None,
                security_categories=categories,
            )
        )
    return permissions


def resource_permissions(
    *,
    view: bool | str = True,
    add_record: bool | str = False,
    edit_record: bool | str = False,
    delete_record: bool | str = False,
    export_records: bool | str = False,
    lock_records: bool = False,
    add_resource: bool = False,
    edit_resource: bool = False,
    delete_resource: bool = False,
    bulk_delete: bool = False,
    manage_collection_links: bool = False,
    manage_users: bool = False,
    manage_roles: bool = False,
    manage_reference_data: bool = False,
    manage_translations: bool = False,
    audit: bool = False,
    share_reports: bool = False,
    publish_reports: bool = False,
    discover: bool = False,
    resolve_duplicates: bool = False,
    share_views: bool = False,
    manage_import_configs: bool = False,
    reviewer_only: bool = False,
) -> list[Permission]:
    """Permissions on a resource, for use in a :class:`Grant`.

    Each argument is ``True``/``False``, or a formula string that restricts
    the operation to matching records, e.g.
    ``edit_record="[partner] == @user.partner"``.

    ``reviewer_only=True`` marks the add/edit record permissions as reviewer
    permissions (the ``"reviewer"`` security category).
    """
    values = dict(locals())
    values.pop("reviewer_only")
    return _permissions(values, reviewer_only=reviewer_only)


def database_permissions(
    *,
    manage_automations: bool = False,
    manage_users: bool = False,
    manage_roles: bool = False,
) -> list[Permission]:
    """Database-wide administrative permissions of a :class:`Role`."""
    return _permissions(dict(locals()))


@dataclass
class Grant:
    """Permissions of a role on one resource (database, folder, form...).

    Args:
        resource_id: Id of the resource; a :class:`Resource` or
            :class:`Database` is accepted too.
        permissions: Usually built with :func:`resource_permissions`.
            Defaults to view only.
        optional: An optional grant only applies to the users to whom the
            resource is explicitly assigned (``resources=`` when adding a
            user or setting their role).
    """

    resource_id: str
    permissions: list[Permission] = field(default_factory=resource_permissions)
    optional: bool = False

    def __post_init__(self) -> None:
        self.resource_id = _id_of(self.resource_id)

    @property
    def operations(self) -> list[Operation | str]:
        return [p.operation for p in self.permissions]

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Grant:
        return cls(
            resource_id=data["resourceId"],
            permissions=[Permission.from_api(p) for p in data.get("operations", [])],
            optional=data.get("optional", False),
        )

    def to_api(self) -> dict[str, Any]:
        return {
            "resourceId": self.resource_id,
            "operations": [p.to_api() for p in self.permissions],
            "optional": self.optional,
        }


@dataclass
class RoleParameter:
    """A per-user value of a role, usable in formulas as ``@user.<id>``.

    Args:
        id: Parameter id, e.g. ``"partner"``.
        label: Human-readable label, e.g. ``"Reporting partner"``.
        range: Id of the reference form whose records are the allowed
            values (a :class:`Form` is accepted), or a formula.
    """

    id: str
    label: str
    range: str

    def __post_init__(self) -> None:
        if not _PARAMETER_ID.match(self.id):
            raise ValueError(
                f"Invalid parameter id {self.id!r}: it must start with a letter "
                "and contain up to 32 letters, digits or underscores."
            )
        self.range = _id_of(self.range)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> RoleParameter:
        return cls(id=data["parameterId"], label=data["label"], range=data["range"])

    def to_api(self) -> dict[str, Any]:
        return {"parameterId": self.id, "label": self.label, "range": self.range}


def role_id_from_label(label: str) -> str:
    """Derive a valid role id from a label: ``"Data entry"`` -> ``"dataentry"``."""
    ascii_label = (
        unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
    )
    slug = re.sub(r"[^a-z0-9]", "", ascii_label.lower()).lstrip("0123456789")
    return slug[:32] or cuid()


@dataclass
class Role:
    """A role that can be assigned to database users.

    Example:
        >>> Role(
        ...     "Data entry",
        ...     grants=[Grant(db, resource_permissions(add_record=True))],
        ...     parameters=[RoleParameter("partner", "Partner", partner_form)],
        ... )

    Args:
        label: Human-readable name, e.g. ``"Viewer"``.
        grants: Permissions per resource.
        permissions: Database-wide permissions, see :func:`database_permissions`.
        parameters: Per-user values usable in grant formulas.
        id: Role id (lower-case letters and digits, max 32). Derived from the
            label if omitted.
    """

    label: str
    grants: list[Grant] = field(default_factory=list)
    permissions: list[Permission] = field(default_factory=list)
    parameters: list[RoleParameter] = field(default_factory=list)
    id: str = ""
    filters: list[dict[str, Any]] = field(default_factory=list, repr=False)
    grant_based: bool = True
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if not self.id:
            self.id = role_id_from_label(self.label)
        if not _ROLE_ID.match(self.id):
            raise ValueError(
                f"Invalid role id {self.id!r}: it must start with a lower-case "
                "letter and contain up to 32 lower-case letters or digits."
            )

    def grant_for(self, resource: Any) -> Grant | None:
        """Return this role's grant on a resource, if any."""
        resource_id = _id_of(resource)
        return next((g for g in self.grants if g.resource_id == resource_id), None)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Role:
        return cls(
            id=data["id"],
            label=data.get("label", ""),
            grants=[Grant.from_api(g) for g in data.get("grants") or []],
            permissions=[Permission.from_api(p) for p in data.get("permissions") or []],
            parameters=[
                RoleParameter.from_api(p) for p in data.get("parameters") or []
            ],
            filters=list(data.get("filters") or []),
            grant_based=data.get("grantBased", True),
            raw=data,
        )

    def to_api(self) -> dict[str, Any]:
        """Serialize as a ``roleUpdates`` entry."""
        return {
            "id": self.id,
            "label": self.label,
            "permissions": [p.to_api() for p in self.permissions],
            "parameters": [p.to_api() for p in self.parameters],
            "filters": self.filters,
            "grants": [g.to_api() for g in self.grants],
            "grantBased": self.grant_based,
        }


@dataclass
class RoleAssignment:
    """The role of a user in a database.

    Args:
        role_id: Id of the role (a :class:`Role` is accepted).
        parameters: Values of the role's parameters, e.g.
            ``{"partner": "<record id>"}``.
        resources: Resources the role applies to (ids or objects). Assign the
            database to give access to everything, or specific folders/forms
            to activate optional grants.
    """

    role_id: str
    parameters: dict[str, str] = field(default_factory=dict)
    resources: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.role_id = _id_of(self.role_id)
        self.resources = [_id_of(r) for r in self.resources]

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> RoleAssignment:
        # The API documentation uses roleId/roleParameters/roleResources, while
        # the server (and the R package) use id/parameters/resources.
        return cls(
            role_id=data.get("id") or data.get("roleId") or "",
            parameters=dict(data.get("parameters") or data.get("roleParameters") or {}),
            resources=list(data.get("resources") or data.get("roleResources") or []),
        )

    def to_api(self) -> dict[str, Any]:
        return {
            "id": self.role_id,
            "parameters": self.parameters,
            "resources": self.resources,
        }
