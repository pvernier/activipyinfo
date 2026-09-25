from __future__ import annotations

from typing import TYPE_CHECKING

from ..ids import cuid
from ._base import ClientBound
from .form import Form

if TYPE_CHECKING:
    from ..client import Client

# It seems that it's not possible to create folder within a folder using the API
# (it's possible from the web app) - to check


def database_update_payload(
    resource_updates: list[dict] | None = None,
    resource_deletions: list[str] | None = None,
) -> dict:
    """Build the body of ``POST /resources/databases/{id}``."""
    return {
        "resourceUpdates": resource_updates or [],
        "resourceDeletions": resource_deletions or [],
        "lockUpdates": [],
        "lockDeletions": [],
        "roleUpdates": [],
        "roleDeletions": [],
        "languageUpdates": [],
        "languageDeletions": [],
        "originalLanguage": None,
        "continuousTranslation": None,
        "translationFromDbMemory": None,
        "thirdPartyTranslation": None,
        "publishedTemplate": None,
    }


class Folder(ClientBound):
    def __init__(
        self,
        label: str,
        id: str | None = None,
        parentId: str | None = None,
        client: Client | None = None,
    ) -> None:
        self.id = cuid() if id is None else id
        self.label = label
        self.parentId = parentId
        self.type = "FOLDER"
        self.visibility = "PRIVATE"
        self.databaseId: str | None = None
        self._client = client

    def build_payload(self) -> dict:
        """Build the database update payload that creates this folder."""
        return database_update_payload(
            resource_updates=[
                {
                    "id": self.id,
                    "parentId": self.parentId,
                    "label": self.label,
                    "type": self.type,
                    "visibility": self.visibility,
                }
            ]
        )

    def __repr__(self):
        return f"Folder({self.id}, {self.label}, {self.parentId})"

    def create_form(self, label: str, fields: list) -> Form:
        """Create a form in the folder."""

        f = Form(label, fields, client=self._client)
        f.databaseId = self.databaseId
        f.parentId = self.id

        self.client.post(f"databases/{self.databaseId}/forms", f.build_payload())
        return f

    def delete_form(self, form: Form | str) -> None:
        """Delete a form from the database."""
        if self.databaseId is None:
            raise ValueError("databaseId must be set before deleting a form.")

        form_id = form.id if isinstance(form, Form) else form
        self.client.post(
            f"databases/{self.databaseId}",
            database_update_payload(resource_deletions=[form_id]),
        )
