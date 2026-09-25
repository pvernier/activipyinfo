from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class _ApiSerializable(Protocol):
    def to_api(self) -> dict[str, Any]: ...


def _as_api(item: dict[str, Any] | _ApiSerializable) -> dict[str, Any]:
    return item if isinstance(item, dict) else item.to_api()


def _id_of(item: str | Any) -> str:
    return item if isinstance(item, str) else item.id


@dataclass
class DatabaseChanges:
    """A batch of changes applied atomically with ``POST /databases/{id}``.

    Folders, forms, roles, locks and languages are all changed through this
    single endpoint. Build a batch, then apply it with
    :meth:`activipyinfo.models.Database.apply` or
    ``client.databases.update(database_id, changes)``.

    Example:
        >>> changes = DatabaseChanges()
        >>> changes.update_resource({"id": "f1", "parentId": "db1",
        ...                          "label": "Folder", "type": "FOLDER"})
        >>> changes.delete_resource("f2")
    """

    resource_updates: list[dict[str, Any]] = field(default_factory=list)
    resource_deletions: list[str] = field(default_factory=list)
    lock_updates: list[dict[str, Any]] = field(default_factory=list)
    lock_deletions: list[str] = field(default_factory=list)
    role_updates: list[dict[str, Any]] = field(default_factory=list)
    role_deletions: list[str] = field(default_factory=list)
    language_updates: list[str] = field(default_factory=list)
    language_deletions: list[str] = field(default_factory=list)
    original_language: str | None = None

    def update_resource(self, resource: dict[str, Any] | _ApiSerializable) -> None:
        """Create or update a folder, form, subform or report entry."""
        self.resource_updates.append(_as_api(resource))

    def delete_resource(self, resource: str | Any) -> None:
        """Delete a resource (and everything it contains) by id or object."""
        self.resource_deletions.append(_id_of(resource))

    def update_lock(self, lock: dict[str, Any] | _ApiSerializable) -> None:
        self.lock_updates.append(_as_api(lock))

    def delete_lock(self, lock: str | Any) -> None:
        self.lock_deletions.append(_id_of(lock))

    def update_role(self, role: dict[str, Any] | _ApiSerializable) -> None:
        self.role_updates.append(_as_api(role))

    def delete_role(self, role: str | Any) -> None:
        self.role_deletions.append(_id_of(role))

    def add_language(self, language: str) -> None:
        self.language_updates.append(language)

    def remove_language(self, language: str) -> None:
        self.language_deletions.append(language)

    def is_empty(self) -> bool:
        return not self.to_api()

    def to_api(self) -> dict[str, Any]:
        """Serialize the batch, leaving out the parts that are unchanged."""
        payload: dict[str, Any] = {
            "resourceUpdates": self.resource_updates,
            "resourceDeletions": self.resource_deletions,
            "lockUpdates": self.lock_updates,
            "lockDeletions": self.lock_deletions,
            "roleUpdates": self.role_updates,
            "roleDeletions": self.role_deletions,
            "languageUpdates": self.language_updates,
            "languageDeletions": self.language_deletions,
            "originalLanguage": self.original_language,
        }
        return {key: value for key, value in payload.items() if value}
