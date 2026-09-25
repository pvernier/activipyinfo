"""HTTP client for the ActivityInfo API."""

from __future__ import annotations

import os
import random
import time
from collections.abc import Callable
from functools import cached_property
from typing import TYPE_CHECKING, Any

import requests

from .__version__ import __version__
from .exceptions import (
    ActivityInfoConnectionError,
    ConfigurationError,
    error_from_response,
)

if TYPE_CHECKING:
    from .models.account import UserAccount
    from .services.databases import DatabasesService

__all__ = ["Client", "DEFAULT_BASE_URL", "TOKEN_ENV_VAR", "BASE_URL_ENV_VAR"]

DEFAULT_BASE_URL = "https://www.activityinfo.org"
TOKEN_ENV_VAR = "ACTIVITYINFO_TOKEN"
BASE_URL_ENV_VAR = "ACTIVITYINFO_BASE_URL"

# Methods that can be retried after a server error or a dropped connection
# without risking a duplicated side effect.
_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})
# 429 means the request was rejected before being processed: always safe to retry.
_RETRY_ANY_METHOD_STATUSES = frozenset({429})
_RETRY_IDEMPOTENT_STATUSES = frozenset({502, 503, 504})
_MAX_RETRY_AFTER = 60.0


class Client:
    """Entry point to the ActivityInfo API.

    Args:
        token: Personal API token or OAuth access token. Defaults to the
            ``ACTIVITYINFO_TOKEN`` environment variable.
        base_url: Server root URL, for self-managed servers. Defaults to the
            ``ACTIVITYINFO_BASE_URL`` environment variable, then
            ``https://www.activityinfo.org``.
        timeout: Timeout in seconds for each HTTP request.
        max_retries: Number of retries after a rate-limit response (429), a
            gateway error (502/503/504) or a connection error. Server errors
            and connection errors are only retried for idempotent methods.
        backoff_factor: Base delay in seconds of the exponential backoff
            between retries (``backoff_factor * 2 ** attempt``, with jitter).
        session: Optional pre-configured :class:`requests.Session`.

    Example:
        >>> client = Client()  # reads ACTIVITYINFO_TOKEN
        >>> client.me().email
        >>> db = client.databases.get("ck8oykh8m5")
    """

    def __init__(
        self,
        token: str | None = None,
        *,
        base_url: str | None = None,
        timeout: float = 30,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        session: requests.Session | None = None,
    ) -> None:
        token = token or os.environ.get(TOKEN_ENV_VAR)
        if not token:
            raise ConfigurationError(
                "No API token provided. Pass token=... or set the "
                f"{TOKEN_ENV_VAR} environment variable."
            )
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")

        self.base_url = (
            base_url or os.environ.get(BASE_URL_ENV_VAR) or DEFAULT_BASE_URL
        ).rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

        self.session = session if session is not None else requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "User-Agent": f"activipyinfo/{__version__}",
            }
        )
        # Indirection so tests can skip the backoff delays.
        self._sleep: Callable[[float], None] = time.sleep

    def __repr__(self) -> str:
        return f"Client(base_url={self.base_url!r})"

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self.session.close()

    # ------------------------------------------------------------------
    # High-level API
    # ------------------------------------------------------------------

    @cached_property
    def databases(self) -> DatabasesService:
        """List, get, create, update and delete databases."""
        from .services.databases import DatabasesService

        return DatabasesService(self)

    def me(self) -> UserAccount:
        """Return the account of the user who owns the API token."""
        from .models.account import UserAccount

        return UserAccount.from_api(self.get("accounts/status")["userAccount"])

    # ------------------------------------------------------------------
    # Low-level HTTP helpers
    # ------------------------------------------------------------------

    def url(self, path: str) -> str:
        """Return the absolute URL of an API path.

        ``path`` is relative to ``<base_url>/resources/`` (e.g. ``"databases"``).
        Absolute ``http(s)://`` URLs are returned unchanged.
        """
        if path.startswith(("http://", "https://")):
            return path
        return f"{self.base_url}/resources/{path.lstrip('/')}"

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        **kwargs: Any,
    ) -> requests.Response:
        """Send a request and return the raw response.

        Retries according to the client's retry policy and raises an
        :class:`~activipyinfo.exceptions.APIError` subclass on HTTP errors.
        Extra keyword arguments are passed to :meth:`requests.Session.request`.
        """
        method = method.upper()
        url = self.url(path)
        kwargs.setdefault("timeout", self.timeout)

        attempt = 0
        while True:
            try:
                response = self.session.request(
                    method, url, params=params, json=json, **kwargs
                )
            except (requests.ConnectionError, requests.Timeout) as exc:
                if attempt < self.max_retries and self._can_retry_exception(
                    method, exc
                ):
                    self._sleep(self._backoff(attempt))
                    attempt += 1
                    continue
                raise ActivityInfoConnectionError(
                    f"{method} {url} failed: {exc}"
                ) from exc

            if attempt < self.max_retries and self._can_retry_status(
                method, response.status_code
            ):
                self._sleep(self._retry_delay(attempt, response))
                attempt += 1
                continue

            if not response.ok:
                raise error_from_response(response)
            return response

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        """GET ``path`` and return the decoded JSON body."""
        return _decode(self.request("GET", path, params=params))

    def post(
        self, path: str, json: Any = None, *, params: dict[str, Any] | None = None
    ) -> Any:
        """POST ``json`` to ``path`` and return the decoded JSON body, if any."""
        return _decode(self.request("POST", path, params=params, json=json))

    def put(
        self, path: str, json: Any = None, *, params: dict[str, Any] | None = None
    ) -> Any:
        """PUT ``json`` to ``path`` and return the decoded JSON body, if any."""
        return _decode(self.request("PUT", path, params=params, json=json))

    def delete(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        """DELETE ``path`` and return the decoded JSON body, if any."""
        return _decode(self.request("DELETE", path, params=params))

    # ------------------------------------------------------------------
    # Retry policy
    # ------------------------------------------------------------------

    @staticmethod
    def _can_retry_status(method: str, status_code: int) -> bool:
        if status_code in _RETRY_ANY_METHOD_STATUSES:
            return True
        return status_code in _RETRY_IDEMPOTENT_STATUSES and method in (
            _IDEMPOTENT_METHODS
        )

    @staticmethod
    def _can_retry_exception(method: str, exc: Exception) -> bool:
        # A connect timeout means the request never reached the server.
        if isinstance(exc, requests.ConnectTimeout):
            return True
        return method in _IDEMPOTENT_METHODS

    def _backoff(self, attempt: int) -> float:
        delay = self.backoff_factor * (2**attempt)
        return delay + random.uniform(0, delay / 2)

    def _retry_delay(self, attempt: int, response: requests.Response) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after is not None:
            try:
                return min(max(float(retry_after), 0.0), _MAX_RETRY_AFTER)
            except ValueError:
                pass
        return self._backoff(attempt)


def _decode(response: requests.Response) -> Any:
    if response.status_code == 204 or not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return response.text
