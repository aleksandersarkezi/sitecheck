# sitecheck

A passive security checker for websites. `sitecheck` makes a handful of
ordinary HTTP/TLS requests to a site — the same requests any browser makes —
and grades what it finds, from **A** (solid security hygiene) to **F**
(missing the basics).

It does **not** scan, fuzz, brute-force, or probe for vulnerabilities. It only
looks at what a normal visitor's browser would already see: response headers,
the TLS certificate, cookies, and whether `http://` redirects to `https://`.

## What it checks

| Check | Why it matters |
| --- | --- |
| **Strict-Transport-Security (HSTS)** | Tells browsers to always use HTTPS for this site, even if a user types `http://` or clicks an old link. Without it, an attacker on the network can downgrade a visitor to plain HTTP and intercept traffic. |
| **Content-Security-Policy (CSP)** | Restricts which scripts, styles, and other resources a page may load. A good CSP is one of the strongest defenses against cross-site scripting (XSS). |
| **X-Frame-Options / CSP `frame-ancestors`** | Controls whether the page can be embedded in an `<iframe>` on another site. Without it, the site is vulnerable to clickjacking. |
| **X-Content-Type-Options** | `nosniff` stops browsers from guessing ("sniffing") a response's content type, which can turn an innocuous upload into executable script. |
| **Referrer-Policy** | Controls how much of the current URL is leaked to third parties via the `Referer` header when a user clicks a link — relevant when URLs contain tokens or other sensitive data. |
| **Permissions-Policy** | Explicitly restricts powerful browser features (camera, microphone, geolocation, etc.), reducing what a compromised or malicious embedded script can do. |
| **TLS certificate** | Checks the certificate is valid, who issued it, how many days remain before expiry (warns under 14 days), and which TLS version was negotiated. An expired or misconfigured certificate breaks trust and can be exploited for interception. |
| **HTTP → HTTPS redirect** | Confirms that plain `http://` traffic is upgraded to `https://`, so visitors who don't type the scheme explicitly still end up encrypted. |
| **Server / X-Powered-By** | Flags headers that unnecessarily reveal server software and version numbers, which makes it easier for an attacker to look up known vulnerabilities. |
| **Cookies** | Checks every `Set-Cookie` header for the `Secure`, `HttpOnly`, and `SameSite` attributes, which protect cookies from network interception, script access (XSS), and cross-site request forgery. |

Each check contributes to an overall 0–100 score, which maps to a letter
grade (A ≥ 90, B ≥ 80, C ≥ 70, D ≥ 60, F below that). The scoring logic lives
in [`src/sitecheck/scoring.py`](src/sitecheck/scoring.py), separate from the
network code, so it can be tested with plain data in isolation.

## Installation

Requires Python 3.11+.

```bash
pip install git+https://github.com/<your-username>/sitecheck.git
```

Or, for local development:

```bash
git clone https://github.com/<your-username>/sitecheck.git
cd sitecheck
pip install -e ".[dev]"
```

## Usage

Check a single site:

```bash
sitecheck example.com
```

Check several sites at once, from a file (one host per line, `#` for comments):

```bash
sitecheck -f urls.txt
```

Machine-readable output, for scripting:

```bash
sitecheck example.com --json
```

Custom network timeout (seconds, default 10):

```bash
sitecheck example.com --timeout 5
```

Use in CI — exit with a non-zero status if any site scores below a grade:

```bash
sitecheck example.com --fail-under C
```

### Example output

```text
$ sitecheck example.com
--------------------------------- example.com ---------------------------------
+-----------------------------------------------------------------------------+
| Check                     | Status | Details                                |
|---------------------------+--------+----------------------------------------|
| Strict-Transport-Security | FAIL   | header missing: browsers may be        |
|                           |        | tricked into using plain HTTP          |
| Content-Security-Policy   | FAIL   | header missing: no mitigation against  |
|                           |        | XSS/injection via content restrictions |
| Frame protection          | FAIL   | no X-Frame-Options and no CSP          |
|                           |        | frame-ancestors: page can be framed    |
|                           |        | (clickjacking risk)                    |
| X-Content-Type-Options    | FAIL   | header missing: browsers may           |
|                           |        | MIME-sniff responses                   |
| Referrer-Policy           | WARN   | header missing: full URLs (possibly    |
|                           |        | with sensitive query params) may leak  |
|                           |        | via Referer                            |
| Permissions-Policy        | WARN   | header missing: browser features       |
|                           |        | (camera, mic, geolocation, ...) are    |
|                           |        | not explicitly restricted              |
| Server                    | INFO   | reveals software name: 'cloudflare'    |
| X-Powered-By              | OK     | header not present                     |
| Cookies                   | INFO   | no cookies set                         |
| TLS Certificate           | OK     | issuer=SSL Corporation, expires in     |
|                           |        | 73d, TLSv1.3                           |
| HTTP -> HTTPS redirect    | FAIL   | http:// does not redirect to HTTPS     |
|                           |        | (ended at http://example.com)          |
+-----------------------------------------------------------------------------+
Score: 33/100  Grade: F
```

(Colors and Unicode box-drawing characters are used automatically when the
terminal supports them.)

## Responsible use

`sitecheck` only sends the same kind of plain GET requests a web browser
sends when a visitor loads a page — it does not attempt logins, submit forms,
enumerate paths, or send anything resembling an attack payload. Even so, only
run it against sites you own or are otherwise authorized to test; sending
automated requests to a site you don't control may violate its terms of
service even when the requests themselves are harmless.

## Development

```bash
pip install -e ".[dev]"
ruff check .
pytest
```

## License

MIT — see [LICENSE](LICENSE).
