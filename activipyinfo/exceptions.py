"""Exceptions raised by activipyinfo."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import requests


class ActivityInfoError(Exception):
    """Base class for every error raised by activipyinfo."""


class ConfigurationError(ActivityInfoError):
    """Raised when the client is misconfigured (e.g. no API token)."""


class ActivityInfoConnectionError(ActivityInfoError):
    """Raised when the server cannot be reached or the request times out."""


class NoMatchError(ActivityInfoError, LookupError):
    """Raised when a lookup by label (or other criteria) matches nothing."""


class MultipleMatchesError(ActivityInfoError, LookupError):
    """Raised when a lookup that expects one result matches several."""


class RecordBatchError(ActivityInfoError):
    """Raised when a batch of record changes fails part-way.

    Attributes:
        submitted: Ids of the records changed by the batches sent before
            the failure (these changes were applied).
        failed: The changes of the batch that failed (not applied).
    """

    def __init__(
        self,
        message: str,
        *,
        submitted: list[str],
        failed: list[dict[str, Any]],
    ) -> None:
        super().__init__(message)
        self.submitted = submitted
        self.failed = failed


class APIError(ActivityInfoError):
    """Raised when the API answers with an HTTP error status.

    Attributes:
        status_code: HTTP status code of the response.
        code: Machine-readable error code from the response body, if any
            (e.g. ``"AUTHENTICATION_REQUIRED"``, ``"NOT_FOUND"``).
        message: Human-readable error message.
        method: HTTP method of the failed request.
        url: URL of the failed request.
        body: Parsed JSON body (or raw text) of the error response.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        code: str | None = None,
        method: str | None = None,
        url: str | None = None,
        body: Any = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.code = code
        self.method = method
        self.url = url
        self.body = body
        super().__init__(str(self))

    def __str__(self) -> str:
        code = f" {self.code}" if self.code else ""
        request = f" ({self.method} {self.url})" if self.method and self.url else ""
        return f"HTTP {self.status_code}{code}: {self.message}{request}"


class BadRequestError(APIError):
    """HTTP 400: the request payload was rejected."""


class AuthenticationError(APIError):
    """HTTP 401: the token is missing, invalid or expired."""


class PermissionDeniedError(APIError):
    """HTTP 403: the token's user is not allowed to perform this action."""


class NotFoundError(APIError):
    """HTTP 404: the resource does not exist or is not visible to the user."""


class ConflictError(APIError):
    """HTTP 409: the change conflicts with the current state of the resource."""


class DeletedError(APIError):
    """HTTP 410: the resource has been deleted."""


class RateLimitError(APIError):
    """HTTP 429: too many requests."""


class ServerError(APIError):
    """HTTP 5xx: the server failed to process the request."""


_STATUS_TO_ERROR: dict[int, type[APIError]] = {
    400: BadRequestError,
    401: AuthenticationError,
    403: PermissionDeniedError,
    404: NotFoundError,
    409: ConflictError,
    410: DeletedError,
    429: RateLimitError,
}


def error_from_response(response: requests.Response) -> APIError:
    """Build the appropriate :class:`APIError` subclass from an error response."""
    status = response.status_code
    if status in _STATUS_TO_ERROR:
        error_class = _STATUS_TO_ERROR[status]
    elif status >= 500:
        error_class = ServerError
    else:
        error_class = APIError

    body: Any
    code = None
    message = None
    try:
        body = response.json()
    except ValueError:
        body = response.text or None

    if isinstance(body, dict):
        code = body.get("code")
        message = body.get("localizedMessage") or body.get("message")
    elif isinstance(body, str) and body.strip():
        message = body.strip()

    return error_class(
        message or response.reason or "Request failed",
        status_code=status,
        code=code,
        method=response.request.method if response.request is not None else None,
        url=response.url,
        body=body,
    )
