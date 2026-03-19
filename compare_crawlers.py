"""
Compare HTTP-only vs Playwright crawling on 10 sites.
Shows how many scripts each method detects.
"""
import asyncio
import re
import sys
from urllib.parse import urlparse

from playwright.async_api import async_playwright
from rich.console import Console
from rich.table import Table

sys.path.insert(0, ".")
from crawler.http_worker import fetch
from crawler.extractor import extract_signals

console = Console()

DOMAINS = [
    "taboolanews.com",
    "sojern.com",
    "merrell.com",
    "formstack.com",
    "writesonic.com",
    "ai21.com",
    "nichesss.com",
    "pushnami.com",
    "usembassy.gov",
    "kuruma-news.jp",
]

# ── HTTP-only crawl ───────────────────────────────────────────────────────────

async def http_crawl(domain: str) -> dict:
    result = await fetch(domain)
    if result.error or not result.body:
        return {"domain": domain, "scripts": [], "error": result.error}

    signals = extract_signals(
        result.url, result.status_code, result.headers, result.body
    )
    return {
        "domain": domain,
        "url": result.url,
        "scripts": signals["script_srcs"],
        "html_globals": signals["js_globals"],
        "error": "",
    }


# ── Playwright crawl ──────────────────────────────────────────────────────────

async def playwright_crawl(domain: str, browser) -> dict:
    url = f"https://{domain}"
    all_requests: list[str] = []

    try:
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            java_script_enabled=True,
            ignore_https_errors=True,
        )
        page = await context.new_page()

        # Intercept ALL network requests
        def on_request(request):
            req_url = request.url
            # Only capture JS files and known tracker/analytics endpoints
            if (
                req_url.endswith(".js")
                or ".js?" in req_url
                or any(
                    kw in req_url
                    for kw in [
                        "gtm", "gtag", "analytics", "pixel", "track",
                        "beacon", "collect", "stat", "counter", "metric",
                        "hotjar", "clarity", "segment", "mixpanel",
                        "amplitude", "heap", "fullstory", "logrocket",
                        "intercom", "drift", "hubspot", "marketo",
                        "facebook", "twitter", "linkedin", "tiktok",
                        "taboola", "outbrain", "criteo", "quantcast",
                        "scorecard", "comscore", "nielsen",
                    ]
                )
            ):
                all_requests.append(req_url)

        page.on("request", on_request)

        # Navigate and wait for network to settle
        try:
            await page.goto(url, wait_until="networkidle", timeout=20000)
        except Exception:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(3)  # extra wait for dynamic scripts
            except Exception as e:
                await context.close()
                return {"domain": domain, "scripts": [], "all_requests": [], "error": str(e)}

        # Also grab script srcs directly from DOM after JS execution
        dom_scripts = await page.evaluate("""
            () => Array.from(document.querySelectorAll('script[src]'))
                      .map(s => s.src)
                      .filter(s => s.length > 0)
        """)

        # Get page content for HTML analysis
        html = await page.content()

        await context.close()

        # Merge: DOM scripts + intercepted network requests
        all_scripts = list(set(dom_scripts + all_requests))

        return {
            "domain": domain,
            "url": url,
            "scripts": dom_scripts,
            "all_requests": all_requests,
            "all_combined": all_scripts,
            "html_len": len(html),
            "error": "",
        }

    except Exception as e:
        return {"domain": domain, "scripts": [], "all_requests": [], "error": str(e)}


# ── Comparison ────────────────────────────────────────────────────────────────

def script_domain(url: str) -> str:
    try:
        return urlparse(url).netloc
    except Exception:
        return url[:40]


async def main():
    console.print("\n[bold cyan]Running HTTP-only crawl...[/]")
    http_results = {}
    for domain in DOMAINS:
        r = await http_crawl(domain)
        http_results[domain] = r
        status = f"[green]{len(r['scripts'])} scripts[/]" if not r["error"] else f"[red]ERR: {r['error'][:50]}[/]"
        console.print(f"  {domain}: {status}")

    console.print("\n[bold cyan]Running Playwright crawl...[/]")
    pw_results = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
        for domain in DOMAINS:
            console.print(f"  {domain}...", end=" ")
            r = await playwright_crawl(domain, browser)
            pw_results[domain] = r
            if r["error"]:
                console.print(f"[red]ERR: {r['error'][:60]}[/]")
            else:
                combined = r.get("all_combined", [])
                console.print(f"[green]{len(r['scripts'])} DOM scripts + {len(r.get('all_requests',[]))} network requests = {len(combined)} total[/]")
        await browser.close()

    # ── Summary table ─────────────────────────────────────────────────────────
    console.print("\n[bold]━━ COMPARISON RESULTS ━━[/]\n")
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("Domain", style="cyan", width=22)
    table.add_column("HTTP scripts", justify="right", style="yellow")
    table.add_column("PW DOM", justify="right", style="green")
    table.add_column("PW Network", justify="right", style="blue")
    table.add_column("PW Total", justify="right", style="bold green")
    table.add_column("Extra found", justify="right", style="magenta")

    total_http = 0
    total_pw = 0
    for domain in DOMAINS:
        h = http_results[domain]
        p = pw_results[domain]

        http_n = len(h.get("scripts", []))
        pw_dom = len(p.get("scripts", []))
        pw_net = len(p.get("all_requests", []))
        pw_total = len(p.get("all_combined", []))
        extra = pw_total - http_n

        total_http += http_n
        total_pw += pw_total

        extra_str = f"[bold magenta]+{extra}[/]" if extra > 0 else str(extra)
        table.add_row(domain, str(http_n), str(pw_dom), str(pw_net), str(pw_total), extra_str)

    console.print(table)
    console.print(f"\nTOTAL: HTTP={total_http} scripts vs Playwright={total_pw} scripts")
    console.print(f"Playwright found [bold magenta]+{total_pw - total_http}[/] extra scripts across all sites\n")

    # ── Detailed diff for each site ───────────────────────────────────────────
    console.print("[bold]━━ SCRIPTS ONLY FOUND BY PLAYWRIGHT ━━[/]\n")
    for domain in DOMAINS:
        h_set = set(http_results[domain].get("scripts", []))
        p_set = set(pw_results[domain].get("all_combined", []))
        new_scripts = p_set - h_set
        if new_scripts:
            console.print(f"[cyan]{domain}[/] (+{len(new_scripts)} new):")
            for s in sorted(new_scripts)[:15]:
                console.print(f"    {s[:100]}")
            if len(new_scripts) > 15:
                console.print(f"    ... and {len(new_scripts) - 15} more")


if __name__ == "__main__":
    asyncio.run(main())
