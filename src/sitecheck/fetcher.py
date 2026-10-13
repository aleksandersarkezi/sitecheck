"""Passive HTTP fetching with user-friendly error messages.

Only ever issues a single, ordinary GET request (plus redirects). No scanning,
no fuzzing, no probing of alternate paths or methods.
"""

from __future__ import annotations

import socket
import ssl

import httpx

USER_AGENT = "sitecheck/0.1 (+https://github.com/; passive security checker)"


class FetchError(Exception):
    """Raised when a site cannot be fetched, with a message safe to show users."""


def fetch(url: str, timeout: float = 10.0) -> httpx.Response:
    """GET `url`, following redirects, raising FetchError on any failure."""
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            return client.get(url)
    except httpx.ConnectTimeout as exc:
        raise FetchError(f"connection timed out after {timeout:.0f}s") from exc
    except httpx.ConnectError as exc:
        raise FetchError(_describe_connect_error(exc)) from exc
    except httpx.TimeoutException as exc:
        raise FetchError(f"request timed out after {timeout:.0f}s") from exc
    except httpx.HTTPError as exc:
        raise FetchError(f"HTTP error: {exc}") from exc


def _describe_connect_error(exc: httpx.ConnectError) -> str:
    cause = exc.__cause__ or exc.__context__
    text = str(exc)
    if isinstance(cause, ssl.SSLCertVerificationError):
        return f"TLS certificate verification failed: {cause.verify_message or cause}"
    dns_markers = ("getaddrinfo failed", "Name or service not known")
    if isinstance(cause, socket.gaierror) or any(marker in text for marker in dns_markers):
        return "DNS resolution failed (host not found)"
    return f"could not connect: {exc}"
