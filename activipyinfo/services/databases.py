from __future__ import annotations

from typing import TYPE_CHECKING

from ..ids import cuid
from ..models._common import one
from ..models.account import BillingAccount
from ..models.changes import DatabaseChanges
from ..models.database import Database

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

    def billing_account(self, database_id: str) -> BillingAccount:
        """Return the billing account that owns a database."""
        return BillingAccount.from_api(
            self._client.get(f"databases/{database_id}/billingAccount")
        )
