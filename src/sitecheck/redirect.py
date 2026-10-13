"""Checks whether plain http:// traffic is redirected to https://."""

from __future__ import annotations

import httpx

from .fetcher import USER_AGENT


def check_https_redirect(host: str, timeout: float = 10.0) -> tuple[bool | None, str]:
    """Return (redirected, message) describing whether http:// upgrades to https://."""
    http_url = f"http://{host}"
    try:
        with httpx.Client(
            follow_redirects=True, timeout=timeout, headers={"User-Agent": USER_AGENT}
        ) as client:
            response = client.get(http_url)
    except httpx.HTTPError as exc:
        return None, f"could not check HTTP redirect: {exc}"

    final_url = str(response.url)
    if final_url.startswith("https://"):
        return True, f"http:// redirects to {final_url}"
    return False, f"http:// does not redirect to HTTPS (ended at {final_url})"
