from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from ._common import parse_time
from .permissions import Grant, RoleAssignment

if TYPE_CHECKING:
    from ..client import Client
    from .permissions import Role


@dataclass(eq=False)
class DatabaseUser:
    """A user invited to a database, with their role and grants."""

    database_id: str
    user_id: str
    email: str
    name: str
    role: RoleAssignment | None = None
    grants: list[Grant] = field(default_factory=list)
    version: int | None = None
    activation_status: str | None = None
    delivery_status: str | None = None
    provisioning_status: str | None = None
    user_license_type: str | None = None
    invite_accepted: bool | None = None
    invite_time: datetime | date | None = None
    last_login_time: datetime | date | None = None
    locked: bool = False
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    _client: Client | None = field(default=None, init=False, repr=False)

    @classmethod
    def from_api(
        cls, data: dict[str, Any], client: Client | None = None
    ) -> DatabaseUser:
        role = data.get("role")
        user = cls(
            database_id=data.get("databaseId", ""),
            user_id=str(data["userId"]),
            email=data.get("email", ""),
            name=data.get("name", ""),
            role=RoleAssignment.from_api(role) if role else None,
            grants=[Grant.from_api(g) for g in data.get("grants") or []],
            version=data.get("version"),
            activation_status=data.get("activationStatus"),
            delivery_status=data.get("deliveryStatus"),
            provisioning_status=data.get("provisioningStatus"),
            user_license_type=data.get("userLicenseType"),
            invite_accepted=data.get("inviteAccepted"),
            invite_time=parse_time(data.get("inviteTime", data.get("inviteDate"))),
            last_login_time=parse_time(
                data.get("lastLoginTime", data.get("lastLoginDate"))
            ),
            locked=data.get("locked", False),
            raw=data,
        )
        user._client = client
        return user

    def __repr__(self) -> str:
        role = self.role.role_id if self.role else None
        return f"DatabaseUser(email={self.email!r}, role={role!r})"

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, DatabaseUser)
            and other.user_id == self.user_id
            and other.database_id == self.database_id
        )

    def __hash__(self) -> int:
        return hash((self.database_id, self.user_id))

    @property
    def client(self) -> Client:
        from ..exceptions import ConfigurationError

        if self._client is None:
            raise ConfigurationError(f"{self!r} is not attached to a Client.")
        return self._client

    def set_role(
        self,
        role: Role | str,
        *,
        resources: list[Any] | None = None,
        parameters: dict[str, str] | None = None,
    ) -> DatabaseUser:
        """Assign another role (or other resources/parameters) to this user."""
        return self.client.users.set_role(
            self.database_id,
            self.user_id,
            role,
            resources=resources,
            parameters=parameters,
        )

    def remove(self) -> None:
        """Remove this user from the database."""
        self.client.users.remove(self.database_id, self.user_id)

    def unlock(self) -> None:
        """Unlock this user's account in the database."""
        self.client.users.unlock(self.database_id, self.user_id)
