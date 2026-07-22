"""Network-boundary controls for user-supplied URLs."""

import contextlib
import socket
from collections.abc import Iterator
from dataclasses import dataclass
from urllib.parse import urljoin

import requests

from app.config import settings
from app.ingestion.validators import validate_public_url


class FetchError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class FetchedPage:
    url: str
    html: str
    content_type: str


DNS_TIMEOUT = 5.0
CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 30.0


@contextlib.contextmanager
def _pin_resolution(hostname: str, addresses: list[str]) -> Iterator[None]:
    yield


def fetch_public_html(url: str) -> FetchedPage:
    current_url = url
    headers = {
        "User-Agent": "Arachnin/0.2 (+https://github.com/M1hawk005/Arachnin)",
        "Accept": "text/html,application/xhtml+xml",
    }

    for redirect_count in range(settings.max_redirects + 1):
        validate_public_url(current_url)
        try:
            original_timeout = socket.getdefaulttimeout()
            socket.setdefaulttimeout(DNS_TIMEOUT)
            try:
                response = requests.get(
                    current_url,
                    headers=headers,
                    timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                    allow_redirects=False,
                    stream=True,
                )
            finally:
                socket.setdefaulttimeout(original_timeout)
        except (requests.Timeout, socket.timeout, TimeoutError) as exc:
            raise FetchError("TIMEOUT", "The request timed out.") from exc
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
