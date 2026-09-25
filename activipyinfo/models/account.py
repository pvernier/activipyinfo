from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ._common import ms_to_datetime


@dataclass
class BillingAccount:
    """A billing account (subscription) that owns databases and user licenses."""

    id: int
    name: str
    code: str | None = None
    plan_name: str | None = None
    status: str | None = None
    trial: bool = False
    expiration_time: datetime | None = None
    user_count: int | None = None
    user_limit: int | None = None
    full_user_limit: int | None = None
    database_count: int | None = None
    capped: bool = False
    parent_billing_account_id: int | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> BillingAccount:
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            code=data.get("code"),
            plan_name=data.get("planName"),
            status=data.get("status"),
            trial=data.get("trial", False),
            expiration_time=ms_to_datetime(data.get("expirationTime")),
            user_count=data.get("userCount"),
            user_limit=data.get("userLimit"),
            full_user_limit=data.get("fullUserLimit"),
            database_count=data.get("databaseCount"),
            capped=data.get("capped", False),
            parent_billing_account_id=data.get("parentBillingAccountId"),
            raw=data,
        )


@dataclass
class UserAccount:
    """The account of the user who owns the API token."""

    id: str
    email: str
    name: str
    locale: str | None = None
    billing_account_id: int | None = None
    billing_role: str | None = None
    platform_role: str | None = None
    activation_status: str | None = None
    delivery_status: str | None = None
    provisioning_status: str | None = None
    idp: str | None = None
    locked: bool = False
    billing_account: BillingAccount | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> UserAccount:
        """Parse the ``userAccount`` object of ``GET /accounts/status``."""
        billing_role = data.get("billingRole") or {}
        billing_account = data.get("billingAccount")
        return cls(
            id=str(data["id"]),
            email=data.get("email", ""),
            name=data.get("name", ""),
            locale=data.get("locale"),
            billing_account_id=data.get(
                "billingAccountId", billing_role.get("billingAccountId")
            ),
            billing_role=billing_role.get("role"),
            platform_role=data.get("platformRole"),
            activation_status=data.get("activationStatus"),
            delivery_status=data.get("deliveryStatus"),
            provisioning_status=data.get("provisioningStatus"),
            idp=data.get("idp") or None,
            locked=data.get("locked", False),
            billing_account=(
                BillingAccount.from_api(billing_account) if billing_account else None
            ),
            raw=data,
        )
