from .client import Client
from .database import Database


class Manager(Client):
    """Legacy entry point, kept until ``client.databases`` replaces it."""

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
