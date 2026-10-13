"""TLS certificate and protocol inspection via a plain TLS handshake.

Opens a single TCP connection and performs a standard TLS handshake (the same
thing any browser does) to read the peer certificate and negotiated
protocol version. No scanning of ciphers, no repeated connections.
"""

from __future__ import annotations

import socket
import ssl
from datetime import datetime, timezone

from .models import TlsInfo

EXPIRY_WARNING_DAYS = 14

_CERT_DATE_FORMAT = "%b %d %H:%M:%S %Y %Z"


def check_tls(host: str, port: int = 443, timeout: float = 10.0) -> TlsInfo:
    """Connect to `host`:`port` and inspect its TLS certificate."""
    context = ssl.create_default_context()
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=host) as tls_sock:
                cert = tls_sock.getpeercert()
                tls_version = tls_sock.version()
    except ssl.SSLCertVerificationError as exc:
        return TlsInfo(valid=False, error=f"certificate verification failed: {exc.verify_message or exc}")
    except socket.gaierror:
        return TlsInfo(valid=False, error="DNS resolution failed (host not found)")
    except TimeoutError:
        return TlsInfo(valid=False, error=f"connection timed out after {timeout:.0f}s")
    except (ssl.SSLError, OSError) as exc:
        return TlsInfo(valid=False, error=f"could not establish TLS connection: {exc}")

    not_after = _parse_not_after(cert)
    days_to_expiry = None
    if not_after is not None:
        days_to_expiry = (not_after - datetime.now(timezone.utc)).days

    return TlsInfo(
        valid=True,
        issuer=_format_name(cert.get("issuer", ())),
        not_after=not_after,
        days_to_expiry=days_to_expiry,
        tls_version=tls_version,
    )


def _parse_not_after(cert: dict) -> datetime | None:
    raw = cert.get("notAfter")
    if not raw:
        return None
    try:
        return datetime.strptime(raw, _CERT_DATE_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _format_name(rdns: tuple) -> str:
    fields: dict[str, str] = {}
    for rdn in rdns:
        for key, value in rdn:
            fields[key] = value
    return fields.get("organizationName") or fields.get("commonName") or "Unknown"
