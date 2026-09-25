from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from ..exceptions import NotFoundError, RecordBatchError
from ..models.form_schema import FormSchema
from ..models.record import Record, RecordHistoryEntry

if TYPE_CHECKING:
    from ..client import Client

MAX_CHANGES_PER_REQUEST = 200


def change(
    form_id: str,
    record_id: str,
    fields: dict[str, Any] | None = None,
    *,
    parent_record_id: str | None = None,
    deleted: bool = False,
) -> dict[str, Any]:
    """Build one entry of the ``changes`` list of ``POST /resources/update``."""
    entry: dict[str, Any] = {"formId": form_id, "recordId": record_id}
    if parent_record_id is not None:
        entry["parentRecordId"] = parent_record_id
    entry["deleted"] = deleted
    entry["fields"] = None if deleted else (fields or {})
    return entry


class RecordsService:
    """Record endpoints, available as ``client.records``.

    These methods take raw field values keyed by field id or code. From a
    form, ``form.records`` checks and converts values using its schema.
    """

    def __init__(self, client: Client) -> None:
        self._client = client

    def get(
        self, form_id: str, record_id: str, schema: FormSchema | None = None
    ) -> Record:
        """Fetch one record."""
        data = self._client.get(f"form/{form_id}/record/{record_id}")
        return Record.from_api(data, schema)

    def exists(self, form_id: str, record_id: str) -> bool:
        """Whether the record exists (and is visible to the user)."""
        try:
            self._client.get(f"form/{form_id}/record/{record_id}")
        except NotFoundError:
            return False
        return True

    def submit(
        self,
        changes: Iterable[dict[str, Any]],
        *,
        batch_size: int = MAX_CHANGES_PER_REQUEST,
    ) -> list[str]:
        """Send record changes, in batches, and return the changed record ids.

        Raises:
            RecordBatchError: a batch failed. Batches sent before it were
                applied; their record ids are in ``error.submitted``.
        """
        if not 1 <= batch_size <= MAX_CHANGES_PER_REQUEST:
            raise ValueError(
                f"batch_size must be between 1 and {MAX_CHANGES_PER_REQUEST}"
            )
        submitted: list[str] = []
        batch: list[dict[str, Any]] = []

        def send() -> None:
            try:
                self._client.post("update", {"changes": batch})
            except Exception as exc:
                raise RecordBatchError(
                    f"A batch of {len(batch)} change(s) failed after "
                    f"{len(submitted)} were applied: {exc}",
                    submitted=list(submitted),
                    failed=list(batch),
                ) from exc
            submitted.extend(c["recordId"] for c in batch)
            batch.clear()

        for entry in changes:
            batch.append(entry)
            if len(batch) == batch_size:
                send()
        if batch:
            send()
        return submitted

    def history(self, form_id: str, record_id: str) -> list[RecordHistoryEntry]:
        """Every change made to a record, oldest first."""
        data = self._client.get(f"form/{form_id}/record/{record_id}/history")
        entries = data.get("entries", []) if isinstance(data, dict) else data or []
        return [RecordHistoryEntry.from_api(e) for e in entries]

    def recover(self, form_id: str, record_id: str) -> None:
        """Restore a deleted record."""
        self._client.post(f"form/{form_id}/record/{record_id}/recover")
