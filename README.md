# sitecheck

A CLI tool that checks a website's security setup: response headers, TLS
certificate, cookies, and whether `http://` actually redirects to `https://`.
Everything it does is a normal request a browser already makes when loading a
page. No scanning, no fuzzing, no probing for vulnerabilities. At the end you
get a score and a letter grade, A through F.

## What it checks

| Check | Why it matters |
| --- | --- |
| **Strict-Transport-Security (HSTS)** | Forces the browser to use HTTPS on every future visit. Without it, someone who types `http://` or clicks an old link can be downgraded to plain HTTP by anyone on the network. |
| **Content-Security-Policy (CSP)** | Probably the single strongest defense against XSS. It locks down which scripts, styles, and resources a page is allowed to load. |
| **X-Frame-Options / CSP `frame-ancestors`** | Stops the page from being loaded in someone else's `<iframe>`. Skip it and you're open to clickjacking. |
| **X-Content-Type-Options** | `nosniff` keeps the browser from guessing content types on its own, a trick that's been used to turn file uploads into executable scripts. |
| **Referrer-Policy** | Controls how much of the current URL leaks to other sites through the `Referer` header when a link gets clicked. Matters a lot if your URLs carry tokens or query params. |
| **Permissions-Policy** | Locks down camera, mic, geolocation, and similar browser features so an injected or third-party script can't just ask for them. |
| **TLS certificate** | Valid or not, who issued it, how many days are left before it expires (flags anything under 14 days), and which TLS version got negotiated. |
| **HTTP → HTTPS redirect** | Confirms plain `http://` traffic actually gets upgraded, not just that the `https://` version happens to work. |
| **Server / X-Powered-By** | Flags headers that hand an attacker a software version for free, saving them a lookup. |
| **Cookies** | Checks every `Set-Cookie` header for `Secure`, `HttpOnly`, and `SameSite`. |

Scoring logic lives in [`src/sitecheck/scoring.py`](src/sitecheck/scoring.py),
kept separate from the networking code so it's testable on its own. A score
of 90+ is an A, 80+ a B, 70+ a C, 60+ a D, anything below that is an F.

## Installation

Requires Python 3.11+.

```bash
pip install git+https://github.com/aleksandersarkezi/sitecheck.git
```

For local development:

```bash
git clone https://github.com/aleksandersarkezi/sitecheck.git
cd sitecheck
pip install -e ".[dev]"
```

## Usage

```bash
sitecheck example.com
```

Check several sites from a file (one host per line, `#` for comments):

```bash
sitecheck -f urls.txt
```

Machine-readable output for scripting:

```bash
sitecheck example.com --json
```

Custom network timeout in seconds (default is 10):

```bash
sitecheck example.com --timeout 5
```

Use it as a CI gate, exits non-zero if any site scores below the given grade:

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

Colors and proper box-drawing characters show up automatically once your
terminal supports them.

## Responsible use

sitecheck only sends the kind of request a browser already sends when
loading a page: no login attempts, no form submissions, no path enumeration.
That said, point it only at sites you own or are otherwise allowed to test.
Automated requests against someone else's site can violate their terms of
service even when nothing you send is actually harmful.

## Development

```bash
pip install -e ".[dev]"
ruff check .
pytest
```

## License

MIT, see [LICENSE](LICENSE).
