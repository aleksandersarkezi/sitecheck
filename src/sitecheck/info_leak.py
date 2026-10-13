"""Checks for headers that unnecessarily reveal server software and versions."""

from __future__ import annotations

import re

import httpx

from .models import CheckItem, Severity

_VERSION_RE = re.compile(r"\d+\.\d+")


def check_info_leaks(headers: httpx.Headers) -> list[CheckItem]:
    """Run all information-disclosure checks."""
    return [
        _check_version_header(headers, "server", "Server"),
        _check_version_header(headers, "x-powered-by", "X-Powered-By"),
    ]


def _check_version_header(headers: httpx.Headers, header_name: str, label: str) -> CheckItem:
    value = headers.get(header_name)
    if value is None:
        return CheckItem(label, Severity.OK, "header not present")
    if _VERSION_RE.search(value):
        return CheckItem(
            label, Severity.WARN, f"reveals software version: {value!r}"
        )
    return CheckItem(label, Severity.INFO, f"reveals software name: {value!r}")
