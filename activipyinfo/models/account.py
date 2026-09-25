from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from ._common import ms_to_datetime, parse_time


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


@dataclass
class BillingAccountUser:
    """A user of a billing account (``GET /billingAccounts/{id}/users``)."""

    user_id: str
    email: str
    name: str
    billing_account_role: str | None = None
    user_license_type: str | None = None
    last_login_time: datetime | date | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> BillingAccountUser:
        return cls(
            user_id=str(data["userId"]),
            email=data.get("email", ""),
            name=data.get("name", ""),
            billing_account_role=data.get("billingAccountRole"),
            user_license_type=data.get("userLicenseType"),
            last_login_time=parse_time(data.get("lastLoginTime")),
            raw=data,
        )


@dataclass
class BillingAccountDatabase:
    """Usage statistics of a database owned by a billing account."""

    database_id: str
    label: str
    description: str | None = None
    owner_id: str | None = None
    owner_email: str | None = None
    form_count: int | None = None
    user_count: int | None = None
    basic_user_count: int | None = None
    record_count: int | None = None
    last_record_update: datetime | date | None = None
    billing_account_id: int | None = None
    suspended: bool = False
    published_template: bool = False
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> BillingAccountDatabase:
        owner = data.get("owner") or {}
        return cls(
            database_id=data["databaseId"],
            label=data.get("label", ""),
            description=data.get("description") or None,
            owner_id=str(owner["id"]) if "id" in owner else None,
            owner_email=owner.get("email"),
            form_count=data.get("formCount"),
            user_count=data.get("userCount"),
            basic_user_count=data.get("basicUserCount"),
            record_count=data.get("recordCount"),
            last_record_update=parse_time(data.get("lastRecordUpdate")),
            billing_account_id=data.get("billingAccountId"),
            suspended=data.get("suspended", False),
            published_template=data.get("publishedTemplate", False),
            raw=data,
        )


@dataclass
class BillingDomain:
    """An email domain whose users belong to a billing account."""

    domain: str
    idp: str | None = None
    delivery_status: str | None = None
    user_count: int | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> BillingDomain:
        return cls(
            domain=data["domain"],
            idp=data.get("idp") or None,
            delivery_status=data.get("deliveryStatus"),
            user_count=data.get("userCount"),
            raw=data,
        )
