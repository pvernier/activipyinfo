import requests


class ActivityInfoError(Exception):
    """Base exception for API errors."""


class ActivityInfoAuthError(ActivityInfoError):
    """Raised when API authentication/authorization fails."""


class ActivityInfoNotFoundError(ActivityInfoError):
    """Raised when a requested resource is not found."""


def request(method: str, url: str, headers: dict, timeout: int, **kwargs):
    """Execute an HTTP request and normalize common API errors."""
    response = requests.request(
        method=method,
        url=url,
        headers=headers,
        timeout=timeout,
        **kwargs,
    )

    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        status_code = response.status_code
        if status_code in (401, 403):
            raise ActivityInfoAuthError(f"Authentication failed: HTTP {status_code}") from exc
        if status_code == 404:
            raise ActivityInfoNotFoundError(f"Resource not found: {url}") from exc
        raise ActivityInfoError(f"Request failed: HTTP {status_code} for {url}") from exc

    return response
