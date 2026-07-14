"""Network-boundary controls for user-supplied URLs."""

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import requests

from app.config import settings


class FetchError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class FetchedPage:
    url: str
    html: str
    content_type: str


def validate_public_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise FetchError("INVALID_URL", "Only public HTTP and HTTPS URLs are supported.")
    if parsed.username or parsed.password:
        raise FetchError("INVALID_URL", "Credentials in URLs are not allowed.")

    try:
        addresses = {
            result[4][0]
            for result in socket.getaddrinfo(
                parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM
            )
        }
    except socket.gaierror as exc:
        raise FetchError("DNS_FAILED", "The hostname could not be resolved.") from exc

    if not addresses:
        raise FetchError("DNS_FAILED", "The hostname did not resolve to an address.")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise FetchError(
                "UNSAFE_DESTINATION", "Private, local, and reserved networks are blocked."
            )


def fetch_public_html(url: str) -> FetchedPage:
    current_url = url
    headers = {
        "User-Agent": "Arachnin/2.0 (+https://github.com/M1hawk005/Arachnin)",
        "Accept": "text/html,application/xhtml+xml",
    }

    for redirect_count in range(settings.max_redirects + 1):
        validate_public_url(current_url)
        try:
            response = requests.get(
                current_url,
                headers=headers,
                timeout=settings.fetch_timeout_seconds,
                allow_redirects=False,
                stream=True,
            )
        except requests.RequestException as exc:
            raise FetchError("FETCH_FAILED", "The document could not be fetched.") from exc

        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise FetchError(
                    "INVALID_REDIRECT", "The destination returned an invalid redirect."
                )
            if redirect_count == settings.max_redirects:
                raise FetchError("TOO_MANY_REDIRECTS", "The destination redirected too many times.")
            current_url = urljoin(current_url, location)
            continue

        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            response.close()
            raise FetchError(
                "UPSTREAM_ERROR", "The destination returned an unsuccessful response."
            ) from exc

        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
            response.close()
            raise FetchError("UNSUPPORTED_CONTENT", "The URL must return an HTML document.")

        declared_size = int(response.headers.get("Content-Length", "0") or 0)
        if declared_size > settings.max_document_bytes:
            response.close()
            raise FetchError(
                "DOCUMENT_TOO_LARGE", "The document exceeds the configured size limit."
            )

        body = bytearray()
        for block in response.iter_content(chunk_size=64 * 1024):
            body.extend(block)
            if len(body) > settings.max_document_bytes:
                response.close()
                raise FetchError(
                    "DOCUMENT_TOO_LARGE", "The document exceeds the configured size limit."
                )
        encoding = response.encoding or response.apparent_encoding or "utf-8"
        final_url = response.url
        response.close()
        return FetchedPage(final_url, body.decode(encoding, errors="replace"), content_type)

    raise FetchError("TOO_MANY_REDIRECTS", "The destination redirected too many times.")
