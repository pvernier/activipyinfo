from __future__ import annotations

import builtins
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import TYPE_CHECKING

from ..ids import cuid
from ..models._common import one
from ..models.account import BillingAccount
from ..models.audit import AUDIT_EVENT_TYPES, AuditEvent
from ..models.changes import DatabaseChanges
from ..models.database import Database
from ..models.job import Job

if TYPE_CHECKING:
    from ..client import Client


class DatabasesService:
    """Database endpoints, available as ``client.databases``."""

    def __init__(self, client: Client) -> None:
        self._client = client

    def list(self) -> list[Database]:
        """List the databases the user can access (summary fields only)."""
        return [
            Database.from_api(item, self._client)
            for item in self._client.get("databases")
        ]

    def get(self, database_id: str) -> Database:
        """Fetch a database with its full tree (resources, roles, locks...)."""
        return Database.from_api(
            self._client.get(f"databases/{database_id}"), self._client
        )

    def find(self, label: str) -> Database:
        """Return the database with this exact label.

        Raises:
            NoMatchError: no database has this label.
            MultipleMatchesError: several databases share this label.
        """
        return one(
            (db for db in self.list() if db.label == label),
            f"database labelled {label!r}",
        )

    def create(
        self,
        label: str,
        *,
        description: str | None = None,
        template_id: str = "",
        id: str | None = None,
    ) -> Database:
        """Create a database owned by the current user.

        Args:
            label: Name of the database.
            description: Optional description.
            template_id: Id of a published template to copy from, if any.
            id: Id of the new database. Generated if omitted.
        """
        payload = {
            "id": id or cuid(),
            "label": label,
            "templateId": template_id,
            "description": description,
        }
        return Database.from_api(self._client.post("databases", payload), self._client)

    def update(self, database_id: str, changes: DatabaseChanges) -> Database:
        """Apply a batch of changes and return the updated database tree."""
        data = self._client.post(f"databases/{database_id}", changes.to_api())
        if not data:
            return self.get(database_id)
        return Database.from_api(data, self._client)

    def delete(self, database_id: str) -> None:
        """Delete a database. Only its owner can do this."""
        self._client.delete(f"databases/{database_id}")

    def duplicate(
        self,
        database_id: str,
        label: str,
        *,
        records: bool = False,
        into: str | None = None,
        timeout: float | None = None,
        progress: Callable[[Job], None] | None = None,
    ) -> Database:
        """Copy a database (forms, folders, roles; optionally its records).

        Args:
            database_id: The database to copy.
            label: Label of the new database (or of the new folder when
                copying ``into`` an existing database).
            records: Copy the records too.
            into: Id of an existing database to copy the forms and folders
                into, instead of creating a new database.

        Returns the new database (or the ``into`` database).
        """
        descriptor: dict[str, object] = {
            "templateDatabaseId": database_id,
            "databaseLabel": label,
            "duplicateRecords": records,
        }
        if into:
            descriptor["targetDatabaseId"] = into
        job = self._client.jobs.run(
            "duplicateDatabase", descriptor, timeout=timeout, progress=progress
        )
        return self.get(job.result.get("databaseId") or into or "")

    def audit_log(
        self,
        database_id: str,
        *,
        before: datetime | None = None,
        after: datetime | None = None,
        resource_id: str | None = None,
        types: Sequence[str] | None = None,
        limit: int = 1000,
    ) -> builtins.list[AuditEvent]:
        """Audit log events, most recent first, like R ``queryAuditLog()``.

        Args:
            before: Only events before this time (default: now).
            after: Only events after this time.
            resource_id: Only events about this form, folder...
            types: Only these event types (see ``AUDIT_EVENT_TYPES``).
            limit: Maximum number of events.
        """
        if limit < 1:
            raise ValueError("limit must be >= 1")
        unknown = set(types or ()) - set(AUDIT_EVENT_TYPES)
        if unknown:
            raise ValueError(
                f"Unknown audit event types {sorted(unknown)}; "
                f"expected some of {AUDIT_EVENT_TYPES}"
            )
        after_ms = _millis(after) if after else 0
        request: dict[str, object] = {
            "resourceFilter": resource_id,
            "typeFilter": list(types or []),
            "startTime": _millis(before or datetime.now()),
        }
        events: builtins.list[AuditEvent] = []
        while True:
            page = self._client.post(f"databases/{database_id}/audit", request)
            for data in page.get("events") or []:
                if (data.get("time") or 0) > after_ms:
                    events.append(AuditEvent.from_api(data))
            end_time = page.get("endTime") or 0
            if (
                not page.get("moreEvents")
                or end_time < after_ms
                or len(events) >= limit
            ):
                return events[:limit]
            request["startTime"] = end_time

    def billing_account(self, database_id: str) -> BillingAccount:
        """Return the billing account that owns a database."""
        return BillingAccount.from_api(
            self._client.get(f"databases/{database_id}/billingAccount")
        )


def _millis(moment: datetime) -> int:
    """Milliseconds since the epoch (naive datetimes are local time)."""
    return int(moment.timestamp() * 1000)
