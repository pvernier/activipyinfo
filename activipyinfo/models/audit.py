from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ._common import ms_to_datetime

__all__ = ["AUDIT_EVENT_TYPES", "AuditEvent"]

AUDIT_EVENT_TYPES = (
    "RECORD",
    "FORM",
    "FOLDER",
    "DATABASE",
    "LOCK",
    "USER_PERMISSION",
    "ROLE",
)


@dataclass
class AuditEvent:
    """An entry of a database's audit log."""

    time: datetime | None
    type: str | None = None
    description: str | None = None
    user_id: str | None = None
    user_name: str | None = None
    user_email: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> AuditEvent:
        user = data.get("user") if isinstance(data.get("user"), dict) else {}
        return cls(
            time=ms_to_datetime(data.get("time")),  # always milliseconds
            type=data.get("type") or data.get("eventType"),
            description=data.get("description"),
            user_id=str(user["id"]) if user and "id" in user else None,
            user_name=user.get("name") if user else None,
            user_email=user.get("email") if user else None,
            raw=data,
        )

    def to_dict(self) -> dict[str, Any]:
        """The event's properties, with the user flattened into ``user.*``."""
        data = {k: v for k, v in self.raw.items() if k != "user"}
        data["time"] = self.time
        data["user.id"] = self.user_id
        data["user.name"] = self.user_name
        data["user.email"] = self.user_email
        return data
