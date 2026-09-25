import json

import pytest
import requests
import responses

from activipyinfo import (
    ActivityInfoConnectionError,
    APIError,
    AuthenticationError,
    BadRequestError,
    Client,
    ConfigurationError,
    ConflictError,
    DeletedError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    __version__,
)
from activipyinfo.client import BASE_URL_ENV_VAR, TOKEN_ENV_VAR

API = "https://www.activityinfo.org/resources"


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------


def test_token_argument_sets_bearer_header():
    client = Client("abc")

    assert client.session.headers["Authorization"] == "Bearer abc"
    assert client.session.headers["User-Agent"] == f"activipyinfo/{__version__}"


def test_token_is_read_from_environment(monkeypatch):
    monkeypatch.setenv(TOKEN_ENV_VAR, "from-env")

    assert Client().session.headers["Authorization"] == "Bearer from-env"


def test_missing_token_raises_configuration_error():
    with pytest.raises(ConfigurationError, match=TOKEN_ENV_VAR):
        Client()


def test_token_is_not_exposed_in_repr():
    assert "secret" not in repr(Client("secret"))


def test_default_base_url():
    assert Client("t").base_url == "https://www.activityinfo.org"


def test_base_url_argument_strips_trailing_slash():
    assert Client("t", base_url="https://ai.example.org/").base_url == (
        "https://ai.example.org"
    )


def test_base_url_is_read_from_environment(monkeypatch):
    monkeypatch.setenv(BASE_URL_ENV_VAR, "https://self-managed.example.org")

    assert Client("t").base_url == "https://self-managed.example.org"


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("databases", f"{API}/databases"),
        ("/databases/db1", f"{API}/databases/db1"),
        ("https://other.example.org/x", "https://other.example.org/x"),
    ],
)
def test_url(path, expected):
    assert Client("t").url(path) == expected


def test_negative_max_retries_is_rejected():
    with pytest.raises(ValueError):
        Client("t", max_retries=-1)


def test_context_manager_closes_session():
    session = requests.Session()
    closed = []
    session.close = lambda: closed.append(True)

    with Client("t", session=session):
        pass

    assert closed == [True]


# ----------------------------------------------------------------------
# Requests and responses
# ----------------------------------------------------------------------


def test_get_returns_decoded_json(client, mocked):
    mocked.get(f"{API}/databases", json=[{"databaseId": "db1"}])

    assert client.get("databases") == [{"databaseId": "db1"}]
    assert mocked.calls[0].request.headers["Authorization"] == "Bearer test-token"


def test_get_passes_query_params(client, mocked):
    mocked.get(
        f"{API}/search",
        match=[responses.matchers.query_param_matcher({"q": "admin"})],
        json=[],
    )

    assert client.get("search", params={"q": "admin"}) == []


def test_post_sends_json_body(client, mocked):
    mocked.post(
        f"{API}/update",
        match=[responses.matchers.json_params_matcher({"changes": []})],
        json={"ok": True},
    )

    assert client.post("update", {"changes": []}) == {"ok": True}


def test_empty_response_body_returns_none(client, mocked):
    mocked.delete(f"{API}/databases/db1/users/u1", status=204)

    assert client.delete("databases/db1/users/u1") is None


def test_non_json_response_returns_text(client, mocked):
    mocked.put(f"{API}/x", body="done", content_type="text/plain")

    assert client.put("x", {}) == "done"


def test_request_uses_client_timeout(mocked):
    client = Client("t", timeout=7)
    seen = {}
    original = client.session.request

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return original(*args, **kwargs)

    client.session.request = spy
    mocked.get(f"{API}/databases", json=[])

    client.get("databases")

    assert seen["timeout"] == 7


# ----------------------------------------------------------------------
# Error mapping
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "error_class"),
    [
        (400, BadRequestError),
        (401, AuthenticationError),
        (403, PermissionDeniedError),
        (404, NotFoundError),
        (409, ConflictError),
        (410, DeletedError),
        (418, APIError),
        (500, ServerError),
    ],
)
def test_http_errors_map_to_exception_classes(status, error_class):
    client = Client("t", max_retries=0)
    with responses.RequestsMock() as mocked:
        mocked.get(f"{API}/databases/db1", status=status)

        with pytest.raises(error_class) as info:
            client.get("databases/db1")

    assert type(info.value) is error_class
    assert info.value.status_code == status


def test_error_keeps_api_code_and_message(client, mocked):
    body = {
        "code": "AUTHENTICATION_REQUIRED",
        "message": "The request must be authenticated",
    }
    mocked.get(f"{API}/databases", status=401, json=body)

    with pytest.raises(AuthenticationError) as info:
        client.get("databases")

    error = info.value
    assert error.code == "AUTHENTICATION_REQUIRED"
    assert error.message == "The request must be authenticated"
    assert error.body == body
    assert error.method == "GET"
    assert error.url == f"{API}/databases"
    assert "AUTHENTICATION_REQUIRED" in str(error)


def test_error_prefers_localized_message(client, mocked):
    body = {"code": "X", "message": "raw", "localizedMessage": "Friendly"}
    mocked.post(f"{API}/update", status=400, json=body)

    with pytest.raises(BadRequestError) as info:
        client.post("update", {})

    assert info.value.message == "Friendly"


def test_error_with_text_body(client, mocked):
    mocked.get(f"{API}/x", status=400, body="Invalid formula")

    with pytest.raises(BadRequestError) as info:
        client.get("x")

    assert info.value.message == "Invalid formula"
    assert info.value.code is None


def test_all_api_errors_share_base_class():
    assert issubclass(NotFoundError, APIError)
    assert issubclass(APIError, Exception)


# ----------------------------------------------------------------------
# Retries
# ----------------------------------------------------------------------


def test_rate_limited_post_is_retried(client, mocked):
    mocked.post(f"{API}/update", status=429)
    mocked.post(f"{API}/update", json={"ok": True})

    assert client.post("update", {"changes": []}) == {"ok": True}
    assert len(mocked.calls) == 2


def test_gateway_error_is_retried_for_get(client, mocked):
    mocked.get(f"{API}/databases", status=503)
    mocked.get(f"{API}/databases", status=502)
    mocked.get(f"{API}/databases", json=[])

    assert client.get("databases") == []
    assert len(mocked.calls) == 3


def test_gateway_error_is_not_retried_for_post(client, mocked):
    mocked.post(f"{API}/jobs", status=503)

    with pytest.raises(ServerError):
        client.post("jobs", {})

    assert len(mocked.calls) == 1


def test_internal_server_error_is_not_retried(client, mocked):
    mocked.get(f"{API}/databases", status=500)

    with pytest.raises(ServerError):
        client.get("databases")

    assert len(mocked.calls) == 1


def test_retries_are_bounded(mocked):
    client = Client("t", max_retries=2)
    client._sleep = lambda s: None
    mocked.get(f"{API}/databases", status=429)

    with pytest.raises(RateLimitError):
        client.get("databases")

    assert len(mocked.calls) == 3


def test_retry_after_header_is_honoured(client, mocked):
    delays = []
    client._sleep = delays.append
    mocked.get(f"{API}/databases", status=429, headers={"Retry-After": "4"})
    mocked.get(f"{API}/databases", json=[])

    client.get("databases")

    assert delays == [4.0]


def test_backoff_grows_exponentially():
    client = Client("t", max_retries=3, backoff_factor=1)
    delays = []
    client._sleep = delays.append
    with responses.RequestsMock() as mocked:
        mocked.get(f"{API}/databases", status=503)

        with pytest.raises(ServerError):
            client.get("databases")

    assert len(delays) == 3
    for attempt, delay in enumerate(delays):
        assert 2**attempt <= delay <= 1.5 * 2**attempt


def test_connection_error_is_retried_for_get(client, mocked):
    mocked.get(f"{API}/databases", body=requests.ConnectionError("reset"))
    mocked.get(f"{API}/databases", json=[])

    assert client.get("databases") == []


def test_connection_error_is_not_retried_for_post(client, mocked):
    mocked.post(f"{API}/update", body=requests.ConnectionError("reset"))

    with pytest.raises(ActivityInfoConnectionError):
        client.post("update", {})

    assert len(mocked.calls) == 1


def test_connect_timeout_is_retried_for_post(client, mocked):
    mocked.post(f"{API}/update", body=requests.ConnectTimeout("slow"))
    mocked.post(f"{API}/update", json={})

    assert client.post("update", {}) == {}


def test_connection_error_after_retries_is_wrapped(client, mocked):
    mocked.get(f"{API}/databases", body=requests.Timeout("slow"))

    with pytest.raises(ActivityInfoConnectionError) as info:
        client.get("databases")

    assert isinstance(info.value.__cause__, requests.Timeout)
    assert len(mocked.calls) == client.max_retries + 1


def test_request_body_is_resent_on_retry(client, mocked):
    mocked.post(f"{API}/update", status=429)
    mocked.post(f"{API}/update", json={})

    client.post("update", {"changes": [1]})

    bodies = [json.loads(call.request.body) for call in mocked.calls]
    assert bodies == [{"changes": [1]}, {"changes": [1]}]
