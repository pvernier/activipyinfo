from unittest.mock import Mock, patch

import requests

from activipyinfo.http import (
    ActivityInfoAuthError,
    ActivityInfoError,
    ActivityInfoNotFoundError,
    request,
)


def test_request_passes_through_success_response():
    with patch("activipyinfo.http.requests.request") as mock_request:
        response = Mock()
        response.raise_for_status.return_value = None
        mock_request.return_value = response

        out = request("GET", "https://example.com", headers={}, timeout=30)

    assert out is response


def test_request_maps_auth_error():
    with patch("activipyinfo.http.requests.request") as mock_request:
        response = Mock()
        response.status_code = 401
        response.raise_for_status.side_effect = requests.HTTPError("401")
        mock_request.return_value = response

        try:
            request("GET", "https://example.com", headers={}, timeout=30)
            assert False, "Expected ActivityInfoAuthError"
        except ActivityInfoAuthError:
            pass


def test_request_maps_not_found_error():
    with patch("activipyinfo.http.requests.request") as mock_request:
        response = Mock()
        response.status_code = 404
        response.raise_for_status.side_effect = requests.HTTPError("404")
        mock_request.return_value = response

        try:
            request("GET", "https://example.com", headers={}, timeout=30)
            assert False, "Expected ActivityInfoNotFoundError"
        except ActivityInfoNotFoundError:
            pass


def test_request_maps_other_http_errors():
    with patch("activipyinfo.http.requests.request") as mock_request:
        response = Mock()
        response.status_code = 500
        response.raise_for_status.side_effect = requests.HTTPError("500")
        mock_request.return_value = response

        try:
            request("GET", "https://example.com", headers={}, timeout=30)
            assert False, "Expected ActivityInfoError"
        except ActivityInfoError:
            pass
