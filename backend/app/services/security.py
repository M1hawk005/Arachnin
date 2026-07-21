"""Network-boundary controls for user-supplied URLs."""

import contextlib
import ipaddress
import socket
from collections.abc import Iterator
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


def validate_public_url(url: str) -> list[str]:
    """Validate a destination and return the global IP addresses it resolves to.

    The returned addresses are pinned for the actual connection (see
    _pin_resolution) so the host that was validated is the host that is fetched,
    closing the rebinding window between this resolution and the one the HTTP
    client would otherwise perform on connect.
    """
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise FetchError("INVALID_URL", "Only public HTTP and HTTPS URLs are supported.")
    if parsed.username or parsed.password:
        raise FetchError("INVALID_URL", "Credentials in URLs are not allowed.")

    default_port = 443 if parsed.scheme == "https" else 80
    try:
        addresses = {
            result[4][0]
            for result in socket.getaddrinfo(
                parsed.hostname, parsed.port or default_port, type=socket.SOCK_STREAM
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
    return sorted(addresses)


def _addrinfo(address: str, port: int) -> tuple:
    family = socket.AF_INET6 if ipaddress.ip_address(address).version == 6 else socket.AF_INET
    sockaddr = (address, port, 0, 0) if family == socket.AF_INET6 else (address, port)
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr)


@contextlib.contextmanager
def _pin_resolution(hostname: str, addresses: list[str]) -> Iterator[None]:
    """Force the HTTP client to connect only to already-validated addresses.

    Celery runs tasks in separate prefork processes, one task at a time, so
    replacing the process-wide resolver for a single connect is safe and is
    always restored afterwards. TLS still verifies the certificate against the
    original hostname because the request URL is unchanged. A network-layer
    egress policy on the worker remains the primary control; this is defense
    in depth at the application layer.
    """
    real_getaddrinfo = socket.getaddrinfo

    def pinned(host, port, *args, **kwargs):
        if host == hostname:
            return [_addrinfo(address, port) for address in addresses]
        return real_getaddrinfo(host, port, *args, **kwargs)

    socket.getaddrinfo = pinned
    try:
        yield
    finally:
        socket.getaddrinfo = real_getaddrinfo


def fetch_public_html(url: str) -> FetchedPage:
    current_url = url
    headers = {
        "User-Agent": "Arachnin/0.2 (+https://github.com/M1hawk005/Arachnin)",
        "Accept": "text/html,application/xhtml+xml",
    }

    for redirect_count in range(settings.max_redirects + 1):
        pinned_addresses = validate_public_url(current_url)
        hostname = urlsplit(current_url).hostname
        pin = (
            _pin_resolution(hostname, pinned_addresses)
            if pinned_addresses and hostname
            else contextlib.nullcontext()
        )
        try:
            with pin:
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
