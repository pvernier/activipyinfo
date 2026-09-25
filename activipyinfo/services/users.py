from __future__ import annotations

import builtins
from typing import TYPE_CHECKING, Any

from ..models.permissions import Grant, Role, RoleAssignment
from ..models.user import DatabaseUser

if TYPE_CHECKING:
    from ..client import Client


def _id_of(value: Any) -> str:
    return value if isinstance(value, str) else value.id


class UsersService:
    """Database user endpoints, available as ``client.users``.

    Every method takes the database id first. From a :class:`Database`,
    ``db.users`` offers the same methods without it.
    """

    def __init__(self, client: Client) -> None:
        self._client = client

    def _path(self, database_id: str, user_id: str | None = None) -> str:
        path = f"databases/{database_id}/users"
        return f"{path}/{user_id}" if user_id else path

    def _user(self, data: Any) -> DatabaseUser:
        return DatabaseUser.from_api(data, self._client)

    def list(self, database_id: str) -> builtins.list[DatabaseUser]:
        """List the users of a database."""
        return [self._user(item) for item in self._client.get(self._path(database_id))]

    def get(self, database_id: str, user_id: str) -> DatabaseUser:
        """Fetch one user of a database, with their role and grants."""
        return self._user(
            self._client.get(f"{self._path(database_id, user_id)}/grants")
        )

    def on_resource(
        self, database_id: str, resource_id: str
    ) -> builtins.list[DatabaseUser]:
        """List the users who have access to a folder or form, with their grants."""
        data = self._client.get(
            f"databases/{database_id}/resources/{resource_id}/grants"
        )
        return [self._user(item) for item in data]

    def add(
        self,
        database_id: str,
        email: str,
        name: str,
        role: Role | str,
        *,
        resources: builtins.list[Any] | None = None,
        parameters: dict[str, str] | None = None,
        locale: str = "en",
    ) -> DatabaseUser:
        """Invite a user to a database with a role.

        Args:
            database_id: The database.
            email: The user's email. If they have no ActivityInfo account,
                they receive an invitation to create one.
            name: The user's name (only used for new accounts).
            role: The role to assign (a :class:`Role` or its id).
            resources: Resources the role applies to (ids or objects).
                Defaults to the whole database.
            parameters: Values of the role's parameters, e.g.
                ``{"partner": "<record id>"}``.
            locale: Language of the invitation email for new accounts.
        """
        assignment = RoleAssignment(
            role_id=_id_of(role),
            parameters=parameters or {},
            resources=resources or [database_id],
        )
        payload = {
            "email": email,
            "name": name,
            "locale": locale,
            "role": assignment.to_api(),
            "grants": [],
        }
        return self._user(self._client.post(self._path(database_id), payload))

    def set_role(
        self,
        database_id: str,
        user_id: str,
        role: Role | str,
        *,
        resources: builtins.list[Any] | None = None,
        parameters: dict[str, str] | None = None,
    ) -> DatabaseUser:
        """Replace a user's role assignment.

        ``resources`` defaults to the whole database.
        """
        assignment = RoleAssignment(
            role_id=_id_of(role),
            parameters=parameters or {},
            resources=resources or [database_id],
        )
        data = self._client.post(
            f"{self._path(database_id, user_id)}/role",
            {"assignments": [assignment.to_api()]},
        )
        return self._user(data) if data else self.get(database_id, user_id)

    def update_grants(
        self,
        database_id: str,
        user_id: str,
        *,
        add: builtins.list[Grant] | None = None,
        remove: builtins.list[Any] | None = None,
    ) -> DatabaseUser:
        """Grant a user permissions on specific resources, outside their role.

        Args:
            add: Grants to create or replace. Record-level formulas are not
                supported by this endpoint; only the operations are sent.
            remove: Resources (ids or objects) whose individual grant to delete.
        """
        payload = {
            "roleUpdates": [],
            "grantUpdates": [
                {
                    "resourceId": grant.resource_id,
                    "operations": [str(op) for op in grant.operations],
                }
                for grant in add or []
            ],
            "grantDeletions": [_id_of(r) for r in remove or []],
        }
        data = self._client.post(f"{self._path(database_id, user_id)}/grants", payload)
        return self._user(data) if data else self.get(database_id, user_id)

    def remove(self, database_id: str, user_id: str) -> None:
        """Remove a user from a database. They are notified by email."""
        self._client.delete(self._path(database_id, user_id))

    def unlock(self, database_id: str, user_id: str) -> None:
        """Unlock a user's account in a database."""
        self._client.post(f"{self._path(database_id, user_id)}/unlock")

    def restore(self, database_id: str, user_id: str) -> DatabaseUser:
        """Restore a removed user with their former role and grants."""
        data = self._client.post(f"{self._path(database_id, user_id)}/restore")
        return self._user(data["restoredUser"])
