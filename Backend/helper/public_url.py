"""Public URL helpers for Stremio and subtitle delivery.

Hugging Face forwards requests to Uvicorn internally.  A saved BASE_URL can be
blank or stale after a Space rename, so delivery links must be able to use the
public request host safely.
"""
from __future__ import annotations

from typing import Optional
from urllib.parse import quote, urlsplit

from Backend.helper.settings_manager import SettingsManager


def _first_header(value: str | None) -> str:
    """Return the first comma-separated proxy header value."""
    return str(value or "").split(",", 1)[0].strip()


def _valid_https_base(value: str) -> Optional[str]:
    """Return a safe public HTTPS base URL, or None when it is unusable."""
    candidate = str(value or "").strip().rstrip("/")
    if not candidate:
        return None
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return None
    if parsed.scheme != "https" or not parsed.netloc:
        return None
    host = parsed.hostname or ""
    if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return None
    return f"https://{parsed.netloc}{parsed.path.rstrip('/')}".rstrip("/")


def public_base_url(request) -> str:
    """Return the configured HTTPS URL or reconstruct the public proxy URL."""
    configured = _valid_https_base(SettingsManager.current().base_url)
    if configured:
        return configured

    headers = request.headers
    forwarded_host = _first_header(headers.get("x-forwarded-host"))
    host = forwarded_host or _first_header(headers.get("host")) or request.url.netloc
    host = host.strip().rstrip("/")

    # Spaces expose HTTPS publicly even though Uvicorn receives an internal
    # HTTP request. Prefer the proxy signal, then use HTTPS for public hosts.
    forwarded_scheme = _first_header(headers.get("x-forwarded-proto"))
    scheme = "https" if forwarded_scheme == "https" or host else request.url.scheme
    return f"{scheme}://{host}".rstrip("/")


def delivery_url(request, token: str, stream_id: str, filename: str) -> str:
    """Build an absolute, safely escaped Telegram delivery URL."""
    return (
        f"{public_base_url(request)}/dl/{quote(str(token), safe='')}/"
        f"{quote(str(stream_id), safe='')}/{quote(str(filename), safe='')}"
    )
