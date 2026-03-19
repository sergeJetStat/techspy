"""
Playwright-based crawler that:
1. Executes JavaScript fully (like a real browser)
2. Intercepts ALL network requests (catches GTM children, pixels, trackers)
3. Extracts DOM scripts AFTER JS execution
4. Falls back to HTTP-only on error
"""
import asyncio
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from playwright.async_api import async_playwright, Browser, BrowserContext

from crawler.extractor import extract_signals

# Script / tracking patterns to capture from network requests
CAPTURE_EXTENSIONS = {".js"}
CAPTURE_KEYWORDS = {
    "gtm", "gtag", "analytics", "pixel", "track", "beacon",
    "collect", "stat", "counter", "metric", "hotjar", "clarity",
    "segment", "mixpanel", "amplitude", "heap", "fullstory",
    "logrocket", "intercom", "drift", "hubspot", "marketo",
    "facebook", "twitter", "linkedin", "tiktok", "taboola",
    "outbrain", "criteo", "quantcast", "scorecard", "comscore",
    "nielsen", "yandex", "metrika", "top-fwz1", "mc.yandex",
    "hit.php", "bing", "bat.bing", "snap", "pinterest",
    "doubleclick", "googlesyndication", "adservice",
}

BROWSER_ARGS = [
    "--no-sandbox",
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
]

_browser: Browser | None = None
_pw_instance = None
_lock = asyncio.Lock()


async def get_browser() -> Browser:
    """Singleton Playwright browser (shared across requests)."""
    global _browser, _pw_instance
    async with _lock:
        if _browser is None or not _browser.is_connected():
            if _pw_instance is not None:
                try:
                    await _pw_instance.stop()
                except Exception:
                    pass
            _pw_instance = await async_playwright().start()
            _browser = await _pw_instance.chromium.launch(
                headless=True,
                args=BROWSER_ARGS,
            )
    return _browser


async def close_browser():
    global _browser, _pw_instance
    if _browser:
        await _browser.close()
        _browser = None
    if _pw_instance:
        await _pw_instance.stop()
        _pw_instance = None


def _should_capture(url: str) -> bool:
    """Return True if this network request URL is worth capturing."""
    low = url.lower()
    path = urlparse(url).path.lower()
    if any(path.endswith(ext) for ext in CAPTURE_EXTENSIONS):
        return True
    if any(kw in low for kw in CAPTURE_KEYWORDS):
        return True
    return False


@dataclass
class PlaywrightResult:
    url: str
    status_code: int
    headers: dict
    body: bytes
    script_srcs: list[str] = field(default_factory=list)   # from <script src>
    network_scripts: list[str] = field(default_factory=list)  # intercepted net
    all_scripts: list[str] = field(default_factory=list)    # union
    error: str = ""


async def fetch_playwright(domain: str, timeout: int = 20_000) -> PlaywrightResult:
    """
    Open domain in headless Chromium, wait for JS to settle,
    intercept network requests, return combined signal set.
    """
    url = f"https://{domain}" if not domain.startswith("http") else domain
    network_scripts: list[str] = []
    main_response = None

    try:
        browser = await get_browser()
        context: BrowserContext = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            java_script_enabled=True,
            ignore_https_errors=True,
            viewport={"width": 1280, "height": 800},
        )

        page = await context.new_page()

        # Intercept requests
        def on_request(request):
            if _should_capture(request.url):
                network_scripts.append(request.url)

        page.on("request", on_request)

        # Navigate
        try:
            resp = await page.goto(
                url,
                wait_until="networkidle",
                timeout=timeout,
            )
            main_response = resp
        except Exception:
            try:
                resp = await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=timeout,
                )
                main_response = resp
                await asyncio.sleep(3)  # extra wait for async scripts
            except Exception as e:
                await context.close()
                return PlaywrightResult(url=url, status_code=0, headers={}, body=b"", error=str(e))

        # DOM scripts (after JS execution)
        dom_scripts: list[str] = await page.evaluate("""
            () => Array.from(document.querySelectorAll('script[src]'))
                      .map(s => s.src)
                      .filter(s => s.startsWith('http'))
        """)

        # Response headers + body (from main navigation)
        status = main_response.status if main_response else 0
        resp_headers = await main_response.all_headers() if main_response else {}
        body = b""
        try:
            body = await main_response.body() if main_response else b""
        except Exception:
            body = (await page.content()).encode("utf-8", errors="replace")

        await context.close()

        all_scripts = list(dict.fromkeys(dom_scripts + network_scripts))  # preserve order, dedupe

        return PlaywrightResult(
            url=page.url,
            status_code=status,
            headers=dict(resp_headers),
            body=body,
            script_srcs=dom_scripts,
            network_scripts=network_scripts,
            all_scripts=all_scripts,
        )

    except Exception as e:
        return PlaywrightResult(url=url, status_code=0, headers={}, body=b"", error=str(e))


def extract_signals_playwright(result: PlaywrightResult) -> dict:
    """
    Convert PlaywrightResult into the same signals dict format used by engine.detect().
    Merges HTTP-level signals with dynamic network script URLs.
    """
    # Start with HTML-level signals from the rendered body
    signals = extract_signals(
        result.url, result.status_code, result.headers, result.body
    )
    # Override script_srcs with the full set (DOM + network)
    signals["script_srcs"] = result.all_scripts
    # Add network-only scripts to html_raw scan (their URLs reveal the tech)
    extra_html = "\n".join(result.network_scripts)
    signals["html_raw"] = signals.get("html_raw", "") + "\n" + extra_html
    return signals
