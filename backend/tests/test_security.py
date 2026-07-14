from unittest.mock import Mock

import pytest

from app.services.security import FetchError, fetch_public_html, validate_public_url


def test_validate_public_url_accepts_global_address(monkeypatch):
    monkeypatch.setattr(
        "app.services.security.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )
    validate_public_url("https://example.com/article")


@pytest.mark.parametrize(
    "url",
    ["file:///etc/passwd", "https://user:secret@example.com", "ftp://example.com/file"],
)
def test_validate_public_url_rejects_unsafe_schemes_and_credentials(url):
    with pytest.raises(FetchError) as error:
        validate_public_url(url)
    assert error.value.code == "INVALID_URL"


def test_validate_public_url_blocks_private_networks(monkeypatch):
    monkeypatch.setattr(
        "app.services.security.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("169.254.169.254", 443))],
    )
    with pytest.raises(FetchError) as error:
        validate_public_url("http://metadata.internal/latest")
    assert error.value.code == "UNSAFE_DESTINATION"


def test_fetch_public_html_follows_only_validated_redirects(monkeypatch):
    validated = []
    monkeypatch.setattr("app.services.security.validate_public_url", validated.append)

    redirect = Mock()
    redirect.is_redirect = True
    redirect.is_permanent_redirect = False
    redirect.headers = {"Location": "/final"}

    success = Mock()
    success.is_redirect = False
    success.is_permanent_redirect = False
    success.headers = {"Content-Type": "text/html; charset=utf-8", "Content-Length": "15"}
    success.encoding = "utf-8"
    success.apparent_encoding = "utf-8"
    success.url = "https://example.com/final"
    success.iter_content.return_value = [b"<p>Hello world</p>"]
    success.raise_for_status.return_value = None
    monkeypatch.setattr("app.services.security.requests.get", Mock(side_effect=[redirect, success]))

    page = fetch_public_html("https://example.com/start")

    assert validated == ["https://example.com/start", "https://example.com/final"]
    assert page.url.endswith("/final")
    assert "Hello world" in page.html


def test_fetch_public_html_rejects_non_html(monkeypatch):
    monkeypatch.setattr("app.services.security.validate_public_url", lambda _: None)
    response = Mock()
    response.is_redirect = False
    response.is_permanent_redirect = False
    response.headers = {"Content-Type": "application/pdf"}
    response.raise_for_status.return_value = None
    monkeypatch.setattr("app.services.security.requests.get", Mock(return_value=response))

    with pytest.raises(FetchError) as error:
        fetch_public_html("https://example.com/report.pdf")
    assert error.value.code == "UNSUPPORTED_CONTENT"
