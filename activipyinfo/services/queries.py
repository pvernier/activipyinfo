from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from ..models.record import QueryResult

if TYPE_CHECKING:
    from ..client import Client


class QueriesService:
    """Column queries over a form's records, available as ``client.queries``.

    Payloads follow the R package's ``queryTable()``.
    """

    def __init__(self, client: Client) -> None:
        self._client = client

    def columns(
        self,
        form_id: str,
        columns: Mapping[str, str] | Sequence[str] | None = None,
        *,
        filter: str | None = None,
        sort: Sequence[tuple[str, str] | str] | None = None,
        offset: int = 0,
        limit: int | None = None,
        truncate_strings: bool = False,
    ) -> QueryResult:
        """Query records of a form as rows.

        Args:
            form_id: The form to query.
            columns: Column id -> formula (usually a field code), or a list
                of formulas used as their own ids. ``"_id"`` is the record id.
                Omitted: every column of the form, with default names.
            filter: A boolean formula, e.g. ``'pcode == "LBN001"'``.
            sort: Formulas to sort by, ascending, or ``(formula, "DESC")``.
            offset: Number of rows to skip.
            limit: Maximum number of rows to return.
            truncate_strings: Let the server shorten long text values.
        """
        if (
            columns is None
            and filter is None
            and sort is None
            and not offset
            and limit is None
        ):
            data = self._client.get(
                f"form/{form_id}/query/columns",
                params={"_truncate": str(truncate_strings).lower()},
            )
            return QueryResult.from_api(data)

        if columns is None:
            raise ValueError("columns are required with filter, sort, offset or limit")
        if isinstance(columns, Mapping):
            named = dict(columns)
        else:
            named = {formula: formula for formula in columns}
        query: dict[str, Any] = {
            "rowSources": [{"rootFormId": form_id}],
            "columns": [
                {"id": column_id, "expression": formula}
                for column_id, formula in named.items()
            ],
            "truncateStrings": truncate_strings,
        }
        if filter:
            query["filter"] = filter
        if sort:
            query["sort"] = [_sort_item(item) for item in sort]
        if offset or limit is not None:
            query["window"] = [offset, limit if limit is not None else 2**31 - 1]
        return QueryResult.from_api(
            self._client.post("query/columns", query), list(named)
        )


def _sort_item(item: tuple[str, str] | str) -> dict[str, str]:
    formula, direction = (item, "ASC") if isinstance(item, str) else item
    direction = direction.upper()
    if direction not in ("ASC", "DESC"):
        raise ValueError(f"Sort direction must be ASC or DESC, not {direction!r}")
    return {"field": formula, "dir": direction}
