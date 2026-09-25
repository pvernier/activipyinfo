from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..models.database import Database
from ..models.form_schema import FormSchema

if TYPE_CHECKING:
    from ..client import Client


class FormsService:
    """Form schema endpoints, available as ``client.forms``.

    From a :class:`Database`, ``db.add_form(...)`` and the methods of
    :class:`~activipyinfo.models.Form` are usually more convenient.
    """

    def __init__(self, client: Client) -> None:
        self._client = client

    def _schema_from(self, data: Any, form_id: str) -> FormSchema:
        """Extract a form's schema from a response, or fetch it.

        Endpoints that change a form answer with the affected forms
        (``{"forms": [{"id": ..., "schema": {...}}]}``), the schema itself,
        or a database tree, depending on the endpoint.
        """
        if isinstance(data, dict):
            for entry in data.get("forms") or []:
                schema = entry.get("schema") or {}
                if entry.get("id") == form_id or schema.get("id") == form_id:
                    return FormSchema.from_api(schema)
            if data.get("id") == form_id and "elements" in data:
                return FormSchema.from_api(data)
        return self.get_schema(form_id)

    def get_schema(self, form_id: str) -> FormSchema:
        """Fetch the current schema of a form."""
        return FormSchema.from_api(self._client.get(f"form/{form_id}/schema"))

    def schema_version(self, form_id: str, version: int) -> FormSchema:
        """Fetch an earlier version of a form's schema."""
        return FormSchema.from_api(
            self._client.get(f"form/{form_id}/schema/versions/{version}")
        )

    def add(self, schema: FormSchema, *, parent_id: str | None = None) -> FormSchema:
        """Create a form (or a subform, if ``schema.parent_form_id`` is set).

        Args:
            schema: The new form; ``schema.database_id`` is required.
            parent_id: Folder that will contain the form. Defaults to the
                database root, or to the parent form for a subform.
        """
        if not schema.database_id:
            raise ValueError("schema.database_id is required to add a form")
        parent = schema.parent_form_id or parent_id or schema.database_id
        payload = {
            "formResource": {
                "id": schema.id,
                "parentId": parent,
                # The R package sends FORM for subforms too.
                "type": "FORM",
                "label": schema.label,
                "visibility": "PRIVATE",
            },
            "formClass": schema.to_api(),
        }
        data = self._client.post(f"databases/{schema.database_id}/forms", payload)
        return self._schema_from(data, schema.id)

    def update_schema(self, schema: FormSchema) -> FormSchema:
        """Replace a form's schema (fields are matched by id)."""
        data = self._client.post(f"form/{schema.id}/schema", schema.to_api())
        return self._schema_from(data, schema.id)

    def recover_field(self, form_id: str, field_id: str) -> FormSchema:
        """Restore a deleted field, with its data."""
        data = self._client.post(f"form/{form_id}/field/{field_id}/recover")
        return self._schema_from(data, form_id)

    def relocate(self, form_id: str, database_id: str) -> None:
        """Move a top-level form, with its subforms and records, to another database."""
        self._client.post(f"form/{form_id}/database", {"databaseId": database_id})

    def duplicate(self, database_id: str, form_id: str) -> Database:
        """Copy a form's structure (not its records); returns the updated tree."""
        data = self._client.post(f"databases/{database_id}/forms/{form_id}/duplicate")
        if isinstance(data, dict) and "databaseId" in data:
            return Database.from_api(data, self._client)
        return self._client.databases.get(database_id)
