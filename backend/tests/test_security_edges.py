from dataclasses import replace
from unittest.mock import Mock

import pytest
import requests

from app.services import security
from app.services.security import FetchError, fetch_public_html


def test_fetch_wraps_timeout_errors(monkeypatch):
    monkeypatch.setattr("app.services.security.validate_public_url", lambda _: None)
    monkeypatch.setattr(
        "app.services.security.requests.get",
        Mock(side_effect=requests.Timeout("timed out")),
    )
    with pytest.raises(FetchError) as error:
        fetch_public_html("https://example.com")
    assert error.value.code == "TIMEOUT"


def test_fetch_wraps_connection_errors(monkeypatch):
    monkeypatch.setattr("app.services.security.validate_public_url", lambda _: None)
    monkeypatch.setattr(
        "app.services.security.requests.get",
        Mock(side_effect=requests.ConnectionError("connection failed")),
    )
    with pytest.raises(FetchError) as error:
        fetch_public_html("https://example.com")
    assert error.value.code == "FETCH_FAILED"


def test_fetch_rejects_declared_oversized_document(monkeypatch):
    monkeypatch.setattr("app.services.security.validate_public_url", lambda _: None)
    response = Mock()
    response.is_redirect = False
    response.is_permanent_redirect = False
    response.headers = {"Content-Type": "text/html", "Content-Length": "999999999"}
    response.raise_for_status.return_value = None
    monkeypatch.setattr("app.services.security.requests.get", Mock(return_value=response))

    with pytest.raises(FetchError) as error:
        fetch_public_html("https://example.com")
    assert error.value.code == "DOCUMENT_TOO_LARGE"


def test_fetch_rejects_stream_that_exceeds_limit(monkeypatch):
    monkeypatch.setattr("app.services.security.validate_public_url", lambda _: None)
    monkeypatch.setattr(security, "settings", replace(security.settings, max_document_bytes=4))
    response = Mock()
    response.is_redirect = False
    response.is_permanent_redirect = False
    response.headers = {"Content-Type": "text/html"}
    response.raise_for_status.return_value = None
    response.iter_content.return_value = [b"12345"]
    monkeypatch.setattr("app.services.security.requests.get", Mock(return_value=response))

    with pytest.raises(FetchError) as error:
        fetch_public_html("https://example.com")
    assert error.value.code == "DOCUMENT_TOO_LARGE"


def test_fetch_rejects_invalid_redirect(monkeypatch):
    monkeypatch.setattr("app.services.security.validate_public_url", lambda _: None)
    response = Mock()
    response.is_redirect = True
    response.is_permanent_redirect = False
    response.headers = {}
    monkeypatch.setattr("app.services.security.requests.get", Mock(return_value=response))

    with pytest.raises(FetchError) as error:
        fetch_public_html("https://example.com")
    assert error.value.code == "INVALID_REDIRECT"
