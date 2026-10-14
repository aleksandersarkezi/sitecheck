"""Server-rendered HTML for the web UI.

No JavaScript and no template engine: a few small functions that build HTML
strings. Every value that comes from a user or a scanned site goes through
`esc()`; a hostile site can put anything into its headers or certificate.
"""

from __future__ import annotations

from html import escape

from .. import __version__
from .store import StoredCheck

SEVERITY_LABEL = {"ok": "OK", "warn": "WARN", "fail": "FAIL", "info": "INFO"}


def esc(value: object) -> str:
    return escape("" if value is None else str(value), quote=True)


def page(body: str, title: str = "sitecheck") -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<link rel="stylesheet" href="/static/style.css">
</head>
<body>
<main>
<header>
  <a class="logo" href="/">sitecheck</a>
  <p class="tagline">Passive security check of a website's headers, TLS and cookies, graded A–F.</p>
</header>
{body}
<footer>
  <p>sitecheck {esc(__version__)} · only sends the requests a browser would ·
  <a href="https://github.com/aleksandersarkezi/sitecheck">source on GitHub</a></p>
</footer>
</main>
</body>
</html>"""


def search_form(value: str = "") -> str:
    return f"""<form class="search" method="get" action="/">
  <label for="host">Website</label>
  <div class="row">
    <input id="host" name="host" type="text" inputmode="url" autocomplete="off"
           placeholder="example.com" value="{esc(value)}" required maxlength="253">
    <button type="submit">Check</button>
  </div>
</form>"""


def error_box(message: str) -> str:
    return f'<p class="error" role="alert">{esc(message)}</p>'


def grade_badge(grade: str | None, size: str = "") -> str:
    g = grade or "?"
    return f'<span class="grade grade-{esc(g.lower())} {esc(size)}">{esc(g)}</span>'


def _check_rows(items: list[dict]) -> str:
    rows = []
    for item in items:
        sev = item.get("severity", "info")
        rows.append(
            f"<tr><td>{esc(item.get('name'))}</td>"
            f'<td><span class="sev sev-{esc(sev)}">{esc(SEVERITY_LABEL.get(sev, sev))}</span></td>'
            f"<td>{esc(item.get('message'))}</td></tr>"
        )
    return "".join(rows)


def report_view(report: dict, cached: bool = False) -> str:
    """Render one report dict (the same shape as `sitecheck --json`)."""
    host = report.get("host")
    if report.get("fetch_error"):
        return f"""<section class="result">
  <div class="summary">{grade_badge("F", "big")}
    <div><h2>{esc(host)}</h2><p>Could not fetch the site: {esc(report["fetch_error"])}</p></div>
  </div>
</section>"""

    tls = report.get("tls") or {}
    if tls.get("valid"):
        tls_row = {
            "name": "TLS Certificate",
            "severity": "warn" if (tls.get("days_to_expiry") or 99) < 14 else "ok",
            "message": f"issuer={tls.get('issuer')}, expires in "
            f"{tls.get('days_to_expiry')}d, {tls.get('tls_version')}",
        }
    else:
        tls_row = {"name": "TLS Certificate", "severity": "fail", "message": tls.get("error")}

    redirect = report.get("redirects_to_https")
    redirect_row = {
        "name": "HTTP → HTTPS redirect",
        "severity": "ok" if redirect else ("fail" if redirect is False else "info"),
        "message": report.get("redirect_message", ""),
    }

    items = (
        list(report.get("header_checks", []))
        + list(report.get("info_leaks", []))
        + list(report.get("cookie_checks", []))
        + [tls_row, redirect_row]
    )
    note = '<p class="muted">Cached result from the last few minutes.</p>' if cached else ""
    return f"""<section class="result">
  <div class="summary">{grade_badge(report.get("grade"), "big")}
    <div><h2>{esc(host)}</h2><p>Score {esc(report.get("score"))}/100</p>{note}</div>
  </div>
  <div class="table-wrap">
  <table>
    <thead><tr><th>Check</th><th>Status</th><th>Details</th></tr></thead>
    <tbody>{_check_rows(items)}</tbody>
  </table>
  </div>
</section>"""


def monitored_view(checks: list[StoredCheck]) -> str:
    if not checks:
        return ""
    rows = []
    for c in checks:
        expiry = "—" if c.days_to_expiry is None else f"{c.days_to_expiry} d"
        status = esc(c.fetch_error) if c.fetch_error else f"{esc(c.score)}/100"
        rows.append(
            f"<tr><td>{grade_badge(c.grade)}</td><td>{esc(c.host)}</td>"
            f"<td>{status}</td><td>{esc(expiry)}</td>"
            f'<td class="muted">{esc(c.checked_at.strftime("%Y-%m-%d %H:%M"))} UTC</td></tr>'
        )
    return f"""<section class="monitored">
  <h2>Monitored sites</h2>
  <div class="table-wrap">
  <table>
    <thead><tr><th>Grade</th><th>Site</th><th>Score</th>
      <th>Cert expires</th><th>Last check</th></tr></thead>
    <tbody>{"".join(rows)}</tbody>
  </table>
  </div>
</section>"""
