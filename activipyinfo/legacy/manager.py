import warnings
from typing import Any

from ..client import Client
from .database import Database


class Manager(Client):
    """Deprecated: use :class:`activipyinfo.Client` and ``client.databases``."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        warnings.warn(
            "Manager is deprecated; use activipyinfo.Client and "
            "client.databases.list() / client.databases.get(id) instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(*args, **kwargs)

    def get_dbs(self) -> list[Database]:
        """List the databases the user has access to."""
        return [
            Database(r["databaseId"], r["label"], client=self)
            for r in self.get("databases")
        ]

    def get_db(self, db_id: str) -> Database | None:
        """Return the database with the given id, or None if not found."""
        for db in self.get_dbs():
            if db.id == db_id:
                return db
        return None
