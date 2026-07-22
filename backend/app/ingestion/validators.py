"""URL validators for ingestion endpoints."""

import ipaddress
from urllib.parse import urlsplit


def validate_public_url(url: str) -> None:
    """Validate URL syntax without performing DNS resolution or network I/O.

    Checks:
    - Scheme must be 'http' or 'https'
    - Hostname must be present
    - Credentials (user:pass@) are rejected
    - Non-global IP-literal targets (private, loopback, link-local, reserved, multicast) are rejected
    """
    from app.services.security import FetchError

    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise FetchError("INVALID_URL", "Only public HTTP and HTTPS URLs are supported.")
    if parsed.username or parsed.password:
        raise FetchError("INVALID_URL", "Credentials in URLs are not allowed.")

    try:
        ip = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        # Domain hostname; DNS resolution is handled during worker fetch
        return None

    if (
        not ip.is_global
        or ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
    ):
        raise FetchError(
            "UNSAFE_DESTINATION", "Private, local, and reserved networks are blocked."
        )
    return None
