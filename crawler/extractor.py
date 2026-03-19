"""
Extract detection signals from an HTTP response.
Returns a structured dict with all signal categories.
"""
import re
import warnings
from urllib.parse import urlparse
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


def extract_signals(url: str, status_code: int, headers: dict, body: bytes) -> dict:
    signals = {
        "url": url,
        "status_code": status_code,
        "headers": _normalize_headers(headers),
        "meta_generator": "",
        "meta_tags": {},
        "html_patterns": [],
        "script_srcs": [],
        "link_hrefs": [],
        "cookies": [],
        "js_globals": [],
        "html_raw": "",
        "is_spa": False,
    }

    try:
        html = body.decode("utf-8", errors="replace")
    except Exception:
        return signals

    signals["html_raw"] = html[:50_000]  # cap at 50KB for matching

    soup = BeautifulSoup(html, "lxml")

    # Meta generator
    gen = soup.find("meta", attrs={"name": re.compile(r"generator", re.I)})
    if gen and gen.get("content"):
        signals["meta_generator"] = gen["content"]

    # All meta tags
    for meta in soup.find_all("meta"):
        name = meta.get("name") or meta.get("property") or ""
        content = meta.get("content") or ""
        if name and content:
            signals["meta_tags"][name.lower()] = content

    # Script srcs
    for script in soup.find_all("script", src=True):
        src = script["src"]
        if src:
            signals["script_srcs"].append(src)

    # Inline script globals (quick scan for window.xxx = or var xxx =)
    for script in soup.find_all("script", src=False):
        text = script.get_text()
        if text:
            # Look for JS globals like __NEXT_DATA__, __NUXT__, gtag, etc.
            for match in re.finditer(r'(?:window\.|var |const |let )(\w+)\s*[=]', text):
                signals["js_globals"].append(match.group(1))
            # Check for data-layer pushes
            if "dataLayer" in text:
                signals["js_globals"].append("dataLayer")

    # Link hrefs (stylesheets + icons for fingerprinting)
    for link in soup.find_all("link", href=True):
        href = link["href"]
        if href:
            signals["link_hrefs"].append(href)

    # Cookies (from Set-Cookie header)
    set_cookie = headers.get("set-cookie", "")
    if set_cookie:
        # Multiple Set-Cookie headers may be joined with newlines
        for cookie_line in set_cookie.split("\n"):
            name_part = cookie_line.split(";")[0].strip()
            if "=" in name_part:
                signals["cookies"].append(name_part.split("=")[0].strip())

    # SPA detection
    signals["is_spa"] = _detect_spa(html, signals)

    return signals


def _normalize_headers(headers: dict) -> dict:
    return {k.lower(): v for k, v in headers.items()}


def _detect_spa(html: str, signals: dict) -> bool:
    spa_indicators = [
        '<div id="root"',
        '<div id="app"',
        '__NEXT_DATA__',
        '__NUXT__',
        '__remixContext',
        'ng-version=',
        'data-reactroot',
        'svelte-',
    ]
    for indicator in spa_indicators:
        if indicator in html:
            return True
    # React/Vue/Angular loaded from CDN
    for src in signals["script_srcs"]:
        if any(fw in src for fw in ["react", "vue", "angular", "ember", "svelte"]):
            return True
    return False
