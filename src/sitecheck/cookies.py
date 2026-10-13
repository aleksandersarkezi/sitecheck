"""Parsing and checking of Set-Cookie headers."""

from __future__ import annotations

import httpx

from .models import CheckItem, CookieInfo, Severity


def parse_cookies(headers: httpx.Headers) -> list[CookieInfo]:
    """Parse every Set-Cookie header into a CookieInfo."""
    return [_parse_cookie(raw) for raw in headers.get_list("set-cookie")]


def _parse_cookie(raw: str) -> CookieInfo:
    parts = [p.strip() for p in raw.split(";")]
    name = parts[0].split("=", 1)[0].strip()
    attrs_lower = {p.lower() for p in parts[1:]}
    secure = "secure" in attrs_lower
    http_only = "httponly" in attrs_lower
    same_site = None
    for part in parts[1:]:
        if part.lower().startswith("samesite="):
            same_site = part.split("=", 1)[1].strip()
    return CookieInfo(name=name, secure=secure, http_only=http_only, same_site=same_site)


def check_cookies(cookies: list[CookieInfo]) -> list[CheckItem]:
    """Check each cookie for the Secure, HttpOnly, and SameSite attributes."""
    if not cookies:
        return [CheckItem("Cookies", Severity.INFO, "no cookies set")]

    items = []
    for cookie in cookies:
        missing = []
        if not cookie.secure:
            missing.append("Secure")
        if not cookie.http_only:
            missing.append("HttpOnly")
        if not cookie.same_site:
            missing.append("SameSite")
        if missing:
            items.append(
                CheckItem(
                    f"Cookie '{cookie.name}'",
                    Severity.WARN,
                    f"missing {', '.join(missing)}",
                )
            )
        else:
            items.append(
                CheckItem(
                    f"Cookie '{cookie.name}'",
                    Severity.OK,
                    f"Secure, HttpOnly, SameSite={cookie.same_site}",
                )
            )
    return items
