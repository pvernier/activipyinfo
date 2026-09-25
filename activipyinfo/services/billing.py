from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..models.account import (
    BillingAccount,
    BillingAccountDatabase,
    BillingAccountUser,
    BillingDomain,
)

if TYPE_CHECKING:
    from ..client import Client


class BillingService:
    """Read-only billing account endpoints, available as ``client.billing``.

    ``account_id`` defaults to the billing account of the token's user.
    """

    def __init__(self, client: Client) -> None:
        self._client = client

    def _path(self, account_id: int | None, suffix: str = "") -> str:
        if account_id is None:
            account_id = self._client.me().billing_account_id
            if account_id is None:
                raise ValueError("The current user has no billing account.")
        return f"billingAccounts/{account_id}{suffix}"

    def get(self, account_id: int | None = None) -> BillingAccount:
        """Return a billing account."""
        return BillingAccount.from_api(self._client.get(self._path(account_id)))

    def users(
        self,
        account_id: int | None = None,
        *,
        owners_only: bool | None = None,
        database_id: str | None = None,
    ) -> list[BillingAccountUser]:
        """List the users of a billing account.

        Args:
            owners_only: Only return the account's owners.
            database_id: Only return users invited to this database.
        """
        params: dict[str, Any] = {}
        if owners_only is not None:
            params["owners"] = str(owners_only).lower()
        if database_id is not None:
            params["databaseId"] = database_id
        data = self._client.get(self._path(account_id, "/users"), params=params or None)
        return [BillingAccountUser.from_api(item) for item in data]

    def databases(self, account_id: int | None = None) -> list[BillingAccountDatabase]:
        """List the databases owned by a billing account, with usage counts."""
        data = self._client.get(self._path(account_id, "/databases"))
        return [BillingAccountDatabase.from_api(item) for item in data]

    def domains(self, account_id: int | None = None) -> list[BillingDomain]:
        """List the email domains of a billing account."""
        data = self._client.get(self._path(account_id, "/domains"))
        return [BillingDomain.from_api(item) for item in data]
