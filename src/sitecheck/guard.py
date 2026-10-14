"""SSRF protection for running sitecheck as a public web service.

When sitecheck runs as a CLI, the person typing the host is the one who owns
the machine, so checking `localhost` is their call. As a web service it's a
different story: anyone on the internet picks the target, and the requests
come from *our* server. Without these checks a visitor could make the server
talk to things only it can reach, e.g. the cloud provider's metadata endpoint
at 169.254.169.254, a database on 127.0.0.1, or other hosts on the private
network.

Two layers:

1. `validate_target()` rejects bad input before anything is sent: ports,
   credentials, paths that try to smuggle a different host, IP literals and
   hostnames that resolve to non-public addresses.
2. `GuardedTransport` re-checks every single request httpx makes, including
   each hop of a redirect chain. A public site answering with
   `301 Location: http://169.254.169.254/` is the classic way around layer 1.

Known limitation: DNS rebinding. The address is checked and then resolved
again when the connection opens, so a hostile DNS server with a very short
TTL could answer differently the second time. Closing that fully means
pinning the checked IP for the connection; the container network setup in
docker-compose.yml is the second line of defence.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from collections.abc import Callable

import httpx

ALLOWED_PORTS = {80, 443}
MAX_HOST_LENGTH = 253

# One or more DNS labels plus a TLD with at least two letters. IDNs must be
# passed in punycode form (xn--...), which this pattern accepts.
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{0,61}[a-z0-9]$"
)

Resolver = Callable[[str], list[str]]


class TargetNotAllowed(ValueError):
    """Raised when a host must not be checked by the public service."""


def default_resolver(host: str) -> list[str]:
    """Return every IPv4/IPv6 address `host` resolves to."""
    infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return sorted({info[4][0] for info in infos})


def is_public_ip(address: str) -> bool:
    """True only for globally routable unicast addresses."""
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def clean_host(raw: str) -> str:
    """Turn user input into a bare lowercase hostname, or raise TargetNotAllowed.

    Accepts `example.com`, `https://example.com` and `https://example.com/path`.
    Rejects anything with a port, credentials, whitespace, or an IP literal.
    """
    value = raw.strip().lower()
    if not value:
        raise TargetNotAllowed("empty host")
    if any(ch.isspace() for ch in value):
        raise TargetNotAllowed("host must not contain whitespace")

    for prefix in ("http://", "https://"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
            break
    else:
        if "://" in value:
            raise TargetNotAllowed("only http:// and https:// are supported")

    # Cut the path, query and fragment *before* looking for '@' and ':', so
    # `example.com/a@b` stays example.com while `user@evil` is rejected.
    for separator in ("/", "?", "#", "\\"):
        value = value.split(separator, 1)[0]

    if "@" in value:
        raise TargetNotAllowed("credentials in the URL are not allowed")
    if ":" in value or value.startswith("["):
        raise TargetNotAllowed("custom ports and IPv6 literals are not allowed")
    value = value.rstrip(".")

    try:
        ipaddress.ip_address(value)
    except ValueError:
        pass
    else:
        raise TargetNotAllowed("IP addresses are not allowed, use a hostname")

    if len(value) > MAX_HOST_LENGTH or not _HOSTNAME_RE.match(value):
        raise TargetNotAllowed("not a valid public hostname")
    return value


def ensure_public(host: str, resolver: Resolver = default_resolver) -> list[str]:
    """Resolve `host` and raise unless *every* address is public."""
    try:
        addresses = resolver(host)
    except (socket.gaierror, UnicodeError) as exc:
        raise TargetNotAllowed("DNS resolution failed (host not found)") from exc
    if not addresses:
        raise TargetNotAllowed("host has no addresses")
    blocked = [addr for addr in addresses if not is_public_ip(addr)]
    if blocked:
        # Don't echo the internal address back to the visitor.
        raise TargetNotAllowed("host resolves to a non-public address")
    return addresses


def validate_target(raw: str, resolver: Resolver = default_resolver) -> str:
    """Full input check for the public service. Returns the clean hostname."""
    host = clean_host(raw)
    ensure_public(host, resolver)
    return host


class GuardedTransport(httpx.BaseTransport):
    """httpx transport that refuses to connect anywhere non-public.

    Runs on every request, so redirect hops are covered as well.
    """

    def __init__(
        self,
        inner: httpx.BaseTransport | None = None,
        resolver: Resolver = default_resolver,
    ) -> None:
        self._inner = inner or httpx.HTTPTransport()
        self._resolver = resolver

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        if url.scheme not in {"http", "https"}:
            raise httpx.ConnectError(f"blocked scheme: {url.scheme}", request=request)
        if url.port is not None and url.port not in ALLOWED_PORTS:
            raise httpx.ConnectError("blocked: only ports 80 and 443 allowed", request=request)
        try:
            clean_host(url.host)
            ensure_public(url.host, self._resolver)
        except TargetNotAllowed as exc:
            raise httpx.ConnectError(f"blocked redirect target: {exc}", request=request) from exc
        return self._inner.handle_request(request)

    def close(self) -> None:
        self._inner.close()
