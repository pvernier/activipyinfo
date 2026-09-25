from __future__ import annotations

from typing import TYPE_CHECKING

from ._base import ClientBound
from .folder import Folder
from .form import Form

if TYPE_CHECKING:
    from .client import Client


class Database(ClientBound):
    def __init__(self, id: str, label: str, client: Client | None = None) -> None:
        self.id = id
        self.label = label
        self._client = client
        self.resources: dict[str, list] = {"folders": [], "forms": []}
        # TODO: add other attributes maybe in a metdata dict

    def __repr__(self):
        return f"Database('{self.id}')"

    def get_resources(self) -> dict[str, list]:
        """Get the resources of the database."""

        tree = self.client.get(f"databases/{self.id}")

        self.resources = {"folders": [], "forms": []}
        for element in tree["resources"]:
            if element["type"] == "FOLDER":
                folder = Folder(
                    element["label"],
                    element["id"],
                    element["parentId"],
                    client=self._client,
                )
                folder.databaseId = self.id
                self.resources["folders"].append(folder)
            elif element["type"] == "FORM":
                form = Form(
                    element["label"],
                    None,
                    element["id"],
                    element["parentId"],
                    client=self._client,
                )
                form.databaseId = self.id
                self.resources["forms"].append(form)
        return self.resources

    def create_folder(self, name: str) -> Folder:
        """Create a folder in the database."""

        f = Folder(name, client=self._client)
        f.databaseId = self.id
        f.parentId = self.id

        self.client.post(f"databases/{self.id}", f.build_payload())
        return f
