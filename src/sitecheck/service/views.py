"""Server-rendered HTML for the web UI.

No JavaScript and no template engine: a few small functions that build HTML
strings. Every value that comes from a user or a scanned site goes through
`esc()`; a hostile site can put anything into its headers or certificate.

The page has to work under a strict CSP (no inline styles or scripts), so
anything dynamic, like the score gauge, is expressed with classes instead of
style attributes.
"""

from __future__ import annotations

import hashlib
import json
from html import escape
from importlib.resources import files

from .. import __version__
from .store import StoredCheck

GITHUB_URL = "https://github.com/aleksandersarkezi/sitecheck"
AUTHOR_NAME = "Aleksander Šarkezi"
AUTHOR_LINKEDIN = "https://www.linkedin.com/in/aleksandersarkezi"
AUTHOR_GITHUB = "https://github.com/aleksandersarkezi"

SITE_DESCRIPTION = (
    "Free website security check. Enter a domain and sitecheck grades its HTTPS setup, "
    "security headers and cookies from A to F."
)


def _asset_version(name: str) -> str:
    """Short content hash for cache busting: a new deploy with a changed file gets
    a new URL, so browsers never mix new HTML with an old stylesheet."""
    data = (files(__package__) / "static" / name).read_bytes()
    return hashlib.sha256(data).hexdigest()[:10]


CSS_URL = f"/static/style.css?v={_asset_version('style.css')}"
GAUGE_SEGMENTS = 20

SEVERITY_LABEL = {"ok": "Pass", "warn": "Warning", "fail": "Fail", "info": "Note"}
SEVERITY_ORDER = {"fail": 0, "warn": 1, "info": 2, "ok": 3}

# Which section of the report each check belongs to, in display order.
GROUPS: list[tuple[str, str, tuple[str, ...]]] = [
    (
        "Connection",
        "Whether visitors always get an encrypted connection.",
        ("TLS Certificate", "HTTP → HTTPS redirect", "Strict-Transport-Security"),
    ),
    (
        "Content protection",
        "Limits on what the page can load and who can embed it.",
        ("Content-Security-Policy", "Frame protection", "X-Content-Type-Options"),
    ),
    (
        "Privacy and permissions",
        "What leaks to other sites and which browser features are allowed.",
        ("Referrer-Policy", "Permissions-Policy"),
    ),
    (
        "What the server reveals",
        "Software names and versions handed out for free.",
        ("Server", "X-Powered-By"),
    ),
]
COOKIE_GROUP = ("Cookies", "Whether cookies are kept away from scripts and plain HTTP.")

EXPLAINER = [
    ("Connection", "A valid certificate, a modern TLS version, and a redirect from http:// "
     "to https:// that browsers are told to remember."),
    ("Content protection", "Headers that stop injected scripts, clickjacking and file-type "
     "tricks."),
    ("Privacy and permissions", "How much of each URL leaks to other sites, and whether "
     "camera, microphone and location are locked down."),
    ("What the server reveals", "Software names and versions an attacker would otherwise "
     "have to look up."),
    ("Cookies", "Secure, HttpOnly and SameSite on every cookie the site sets."),
]


def esc(value: object) -> str:
    return escape("" if value is None else str(value), quote=True)


def grade_class(grade: str | None) -> str:
    g = (grade or "").lower()
    return f"g-{g}" if g in {"a", "b", "c", "d", "f"} else "g-none"


def _structured_data(base_url: str) -> str:
    """schema.org JSON-LD so search engines know what the page is and who made it.

    It's a data block, not a script, so it runs under a CSP with no script-src.
    `</` is escaped so the JSON can never close the surrounding tag.
    """
    data = {
        "@context": "https://schema.org",
        "@type": "WebApplication",
        "name": "sitecheck",
        "url": base_url,
        "description": SITE_DESCRIPTION,
        "applicationCategory": "SecurityApplication",
        "operatingSystem": "Any",
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "EUR"},
        "author": {
            "@type": "Person",
            "name": AUTHOR_NAME,
            "url": AUTHOR_LINKEDIN,
            "sameAs": [AUTHOR_LINKEDIN, AUTHOR_GITHUB],
        },
        "codeRepository": GITHUB_URL,
    }
    text = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return f'<script type="application/ld+json">{text}</script>'


def page(
    body: str,
    title: str = "sitecheck",
    base_url: str = "/",
    indexable: bool = True,
) -> str:
    """Wrap `body` in the full HTML document.

    Only the plain home page is indexable. Result pages (`/?host=...`) are
    `noindex`: there are infinitely many of them, they'd be thin duplicate
    content, and nobody should be able to make a search engine list a
    stranger's site with an F next to it under this domain.
    """
    base = base_url if base_url.endswith("/") else base_url + "/"
    if indexable:
        seo = f"""<link rel="canonical" href="{esc(base)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="sitecheck">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(SITE_DESCRIPTION)}">
<meta property="og:url" content="{esc(base)}">
<meta property="og:image" content="{esc(base)}static/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="author" content="{esc(AUTHOR_NAME)}">
{_structured_data(base)}"""
    else:
        seo = '<meta name="robots" content="noindex, follow">'
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{esc(SITE_DESCRIPTION)}">
<title>{esc(title)}</title>
{seo}
<link rel="icon" href="/static/favicon.svg" type="image/svg+xml">
<link rel="preload" href="/static/fonts/archivo.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{CSS_URL}">
</head>
<body>
<div class="wrap">
<header class="top">
  <a class="brand" href="/">sitecheck</a>
  <a class="top-link" href="{GITHUB_URL}">Source on GitHub</a>
</header>
<main>
{body}
</main>
<footer class="foot">
  <p>Built and run by {esc(AUTHOR_NAME)}
  (<a href="{AUTHOR_LINKEDIN}" rel="author">LinkedIn</a>,
  <a href="{AUTHOR_GITHUB}">GitHub</a>).</p>
  <p>sitecheck {esc(__version__)}. It only sends the requests a browser sends when it loads
  a page, so it never logs in, submits forms or probes for hidden paths. Check sites you
  own or have permission to test.</p>
</footer>
</div>
</body>
</html>"""


def robots_txt(base_url: str) -> str:
    base = base_url if base_url.endswith("/") else base_url + "/"
    return (
        "User-agent: *\n"
        "Disallow: /api/\n"
        "Disallow: /metrics\n"
        "Allow: /\n"
        f"\nSitemap: {base}sitemap.xml\n"
    )


def sitemap_xml(base_url: str) -> str:
    base = base_url if base_url.endswith("/") else base_url + "/"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url><loc>{esc(base)}</loc></url>\n"
        "</urlset>\n"
    )


def hero(value: str = "", compact: bool = False) -> str:
    heading = (
        ""
        if compact
        else """<h1>How well is this website protected?</h1>
  <p class="lede">Enter a domain. sitecheck looks at its HTTPS setup, security headers and
  cookies the way a browser would, and grades it from A to F.</p>"""
    )
    return f"""<section class="hero{' compact' if compact else ''}">
  {heading}
  <form class="check-form" method="get" action="/">
    <label for="host">Website address</label>
    <div class="field">
      <input id="host" name="host" type="text" inputmode="url" autocomplete="off"
             autocapitalize="off" spellcheck="false" placeholder="example.com"
             value="{esc(value)}" required maxlength="253">
      <button type="submit">Check site</button>
    </div>
  </form>
</section>"""


def explainer() -> str:
    items = "".join(f"<dt>{esc(name)}</dt><dd>{esc(text)}</dd>" for name, text in EXPLAINER)
    return f"""<section class="explainer">
  <h2>What gets checked</h2>
  <dl>{items}</dl>
  <p class="scale">90 points or more is an A, 80 a B, 70 a C, 60 a D. Anything lower is an F.
  A site that can't be reached at all gets an F as well.</p>
</section>"""


def error_box(message: str, status: int = 400) -> str:
    text = esc(_sentence(message.rstrip(".")))
    if status == 400:
        return f"""<section class="notice" role="alert">
  <h2>Can't check that address</h2>
  <p>{text}. Enter a public domain name such as <code>example.com</code>.</p>
</section>"""
    return f"""<section class="notice" role="alert">
  <h2>Try again shortly</h2>
  <p>{text}.</p>
</section>"""


def _gauge(score: int | None, grade: str | None) -> str:
    filled = round((score or 0) / 100 * GAUGE_SEGMENTS)
    segments = "".join(
        f'<span class="seg{" on" if i < filled else ""}"></span>' for i in range(GAUGE_SEGMENTS)
    )
    return (
        f'<div class="gauge {grade_class(grade)}" role="img" '
        f'aria-label="Score {esc(score)} out of 100">{segments}</div>'
    )


def _tls_item(tls: dict) -> dict:
    if not tls.get("valid"):
        return {"name": "TLS Certificate", "severity": "fail", "message": tls.get("error")}
    days = tls.get("days_to_expiry")
    soon = days is not None and days < 14
    return {
        "name": "TLS Certificate",
        "severity": "warn" if soon else "ok",
        "message": f"Issued by {tls.get('issuer')}, expires in {days} days, "
        f"{tls.get('tls_version')}",
    }


def _redirect_item(report: dict) -> dict:
    redirect = report.get("redirects_to_https")
    severity = "ok" if redirect else ("fail" if redirect is False else "info")
    return {
        "name": "HTTP → HTTPS redirect",
        "severity": severity,
        "message": report.get("redirect_message", ""),
    }


def _summary(items: list[dict]) -> str:
    fails = sum(1 for i in items if i.get("severity") == "fail")
    warns = sum(1 for i in items if i.get("severity") == "warn")
    if not fails and not warns:
        return f"All {len(items)} checks passed."
    parts = []
    if fails:
        parts.append(f"{fails} problem{'s' if fails != 1 else ''}")
    if warns:
        parts.append(f"{warns} warning{'s' if warns != 1 else ''}")
    return " and ".join(parts) + f" out of {len(items)} checks."


def _sentence(text: object) -> str:
    """Capitalise the first letter of a check message for display."""
    value = "" if text is None else str(text)
    return value[:1].upper() + value[1:]


def _check_list(items: list[dict]) -> str:
    rows = []
    for item in sorted(items, key=lambda i: SEVERITY_ORDER.get(i.get("severity"), 9)):
        sev = item.get("severity", "info")
        rows.append(
            f'<li class="check s-{esc(sev)}">'
            f'<span class="status">{esc(SEVERITY_LABEL.get(sev, sev))}</span>'
            f'<span class="name">{esc(item.get("name"))}</span>'
            f'<span class="detail">{esc(item.get("message"))}</span></li>'
        )
    return f'<ul class="checks">{"".join(rows)}</ul>'


def _group(title: str, blurb: str, items: list[dict]) -> str:
    if not items:
        return ""
    return f"""<section class="group">
    <h3>{esc(title)}</h3>
    <p class="blurb">{esc(blurb)}</p>
    {_check_list(items)}
  </section>"""


def report_view(report: dict, cached: bool = False) -> str:
    """Render one report dict (the same shape as `sitecheck --json`)."""
    host = report.get("host")
    if report.get("fetch_error"):
        return f"""<article class="report g-f">
  <div class="verdict">
    <p class="letter" aria-label="Grade F">F</p>
    <div class="verdict-text">
      <h2>{esc(host)}</h2>
      <p>The site couldn't be loaded, so nothing else could be checked:
      {esc(report["fetch_error"])}.</p>
    </div>
  </div>
</article>"""

    tls = report.get("tls") or {}
    items = (
        [_tls_item(tls), _redirect_item(report)]
        + list(report.get("header_checks", []))
        + list(report.get("info_leaks", []))
    )
    cookies = list(report.get("cookie_checks", []))

    by_name = {item.get("name"): item for item in items}
    used: set[str] = set()
    groups_html = []
    for title, blurb, names in GROUPS:
        group_items = [by_name[n] for n in names if n in by_name]
        used.update(names)
        groups_html.append(_group(title, blurb, group_items))
    leftovers = [i for i in items if i.get("name") not in used]
    groups_html.append(_group("Other", "Checks outside the groups above.", leftovers))
    groups_html.append(_group(*COOKIE_GROUP, cookies))

    grade = report.get("grade")
    score = report.get("score")
    cached_note = (
        '<p class="cached">Checked in the last 10 minutes, so this is the saved result.</p>'
        if cached
        else ""
    )
    return f"""<article class="report {grade_class(grade)}">
  <div class="verdict">
    <p class="letter" aria-label="Grade {esc(grade)}">{esc(grade)}</p>
    <div class="verdict-text">
      <h2>{esc(host)}</h2>
      <p class="score">Score {esc(score)}/100. {esc(_summary(items + cookies))}</p>
      {_gauge(score, grade)}
      {cached_note}
    </div>
  </div>
  {"".join(groups_html)}
</article>"""


def monitored_view(checks: list[StoredCheck]) -> str:
    if not checks:
        return ""
    rows = []
    for c in checks:
        if c.fetch_error:
            status = '<span class="down">Unreachable</span>'
        else:
            status = f"{esc(c.score)}/100"
        expiry = "–" if c.days_to_expiry is None else f"{c.days_to_expiry} days left"
        rows.append(
            f'<tr><td><span class="chip {grade_class(c.grade)}">{esc(c.grade or "?")}</span></td>'
            f'<td class="host">{esc(c.host)}<span class="host-sub">{status}</span></td>'
            f'<td class="col-score">{status}</td><td class="col-cert">{esc(expiry)}</td>'
            f'<td class="when col-when">{esc(c.checked_at.strftime("%d %b %H:%M"))} UTC</td></tr>'
        )
    return f"""<section class="watched">
  <h2>Sites this server keeps an eye on</h2>
  <p class="blurb">Re-checked every few hours. A drop in grade, an outage or a certificate
  close to expiry sends an alert.</p>
  <div class="table-wrap">
  <table>
    <thead><tr>
      <th scope="col">Grade</th>
      <th scope="col">Site</th>
      <th scope="col" class="col-score">Score</th>
      <th scope="col" class="col-cert">Certificate</th>
      <th scope="col" class="col-when">Last check</th>
    </tr></thead>
    <tbody>{"".join(rows)}</tbody>
  </table>
  </div>
</section>"""
