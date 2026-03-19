"""
Main pipeline: ties together crawler, extractor, detection engine, and DB storage.
"""
import asyncio
import time
from dataclasses import dataclass
from rich.console import Console
from rich.table import Table

from config import MAX_CONCURRENT_CRAWLS, UNKNOWN_SIGNALS_THRESHOLD, ANTHROPIC_API_KEY, USE_PLAYWRIGHT
from db.store import get_db, init_db, upsert_site, update_site_crawled, save_detections, record_unknown_signal, get_stats
from crawler.http_worker import fetch
from crawler.extractor import extract_signals
from detection.engine import detect, detections_to_dict, find_unknown_signals
from crawler.dns_detect import detect_dns, dns_detections_to_dict
from agents.detection_agent import run_detection_agent

console = Console()


@dataclass
class CrawlResult:
    domain: str
    url: str
    status_code: int
    detections: list[dict]
    crawl_time: float
    error: str = ""



async def crawl_and_store(domain: str, verbose: bool = True) -> CrawlResult:
    """Crawl a domain, detect technologies, persist results to the database."""
    t0 = time.monotonic()

    detections_list: list[dict] = []
    detections_obj = []
    signals = {}
    error = ""
    final_url = f"https://{domain}"
    status_code = 0

    if USE_PLAYWRIGHT:
        # ── Playwright: headless browser, catches GTM-loaded scripts ──────────
        from crawler.playwright_worker import fetch_playwright, extract_signals_playwright
        try:
            pw_result = await fetch_playwright(domain)
            error = pw_result.error
            final_url = pw_result.url or final_url
            status_code = pw_result.status_code
            if not error and pw_result.status_code > 0:
                signals = extract_signals_playwright(pw_result)
                detections_obj = detect(signals)
                detections_list = detections_to_dict(detections_obj)
        except Exception as e:
            error = str(e)
        # Fallback to HTTP on Playwright failure
        if error:
            fetch_result = await fetch(domain)
            error = fetch_result.error
            final_url = fetch_result.url
            status_code = fetch_result.status_code
            if not error and fetch_result.status_code > 0:
                signals = extract_signals(
                    fetch_result.url, fetch_result.status_code,
                    fetch_result.headers, fetch_result.body
                )
                detections_obj = detect(signals)
                detections_list = detections_to_dict(detections_obj)
    else:
        # ── HTTP-only (fast, low RAM) ──────────────────────────────────────────
        fetch_result = await fetch(domain)
        error = fetch_result.error
        final_url = fetch_result.url
        status_code = fetch_result.status_code
        if not error and fetch_result.status_code > 0:
            signals = extract_signals(
                fetch_result.url, fetch_result.status_code,
                fetch_result.headers, fetch_result.body
            )
            detections_obj = detect(signals)
            detections_list = detections_to_dict(detections_obj)

    # DNS detection runs independently (even on HTTP errors)
    try:
        dns_detections = await asyncio.wait_for(detect_dns(domain), timeout=6.0)
        dns_list = dns_detections_to_dict(dns_detections)
        # Merge: add DNS results not already detected
        existing_techs = {d["tech"] for d in detections_list}
        for d in dns_list:
            if d["tech"] not in existing_techs:
                detections_list.append(d)
    except Exception:
        dns_list = []

    result = CrawlResult(
        domain=domain,
        url=final_url,
        status_code=status_code,
        detections=detections_list,
        crawl_time=time.monotonic() - t0,
        error=error,
    )

    db = await get_db()
    try:
        site_id = await upsert_site(db, domain)
        await update_site_crawled(db, domain, status_code)

        if detections_list:
            await save_detections(db, site_id, detections_list)

        if signals:
            unknowns = find_unknown_signals(signals, detections_obj)
            for unk in unknowns[:5]:
                await record_unknown_signal(db, unk["signal_type"], unk["signal_value"], domain)

        if verbose:
            _print_result(result)

    finally:
        await db.close()

    return result


async def crawl_batch(domains: list[str], use_scheduler: bool = True) -> list[CrawlResult]:
    """Crawl multiple domains concurrently. Optionally use the Crawl Scheduler agent."""
    await init_db()

    if use_scheduler and len(domains) > 1:
        from agents.crawl_scheduler import run_crawl_scheduler
        await run_crawl_scheduler(domains)

    sem = asyncio.Semaphore(MAX_CONCURRENT_CRAWLS)

    async def _bounded(domain: str) -> CrawlResult:
        async with sem:
            return await crawl_and_store(domain, verbose=False)

    console.print(f"\n[bold]Crawling {len(domains)} domains[/] (concurrency={MAX_CONCURRENT_CRAWLS})")
    tasks = [_bounded(d) for d in domains]
    results = await asyncio.gather(*tasks)

    _print_batch_summary(list(results))

    # Check if Detection Agent should run
    db = await get_db()
    try:
        stats = await get_stats(db)
    finally:
        await db.close()

    # Count unprocessed unknown signals
    from db.store import get_unknown_signals
    db2 = await get_db()
    try:
        unknowns = await get_unknown_signals(db2, min_count=1, limit=1000)
    finally:
        await db2.close()

    if len(unknowns) >= UNKNOWN_SIGNALS_THRESHOLD:
        if not ANTHROPIC_API_KEY:
            console.print(f"\n[dim]{len(unknowns)} unknown signals ready - set ANTHROPIC_API_KEY to run Detection Agent[/]")
        else:
            console.print(f"\n[yellow]>> {len(unknowns)} unknown signals accumulated -- triggering Detection Agent[/]")
            await run_detection_agent(min_signal_count=2)

    return list(results)


def _print_result(result: CrawlResult):
    if result.error:
        console.print(f"[red]ERR {result.domain}[/] -- {result.error}")
        return

    console.print(f"\n[bold green]OK {result.domain}[/] [{result.status_code}] {result.crawl_time:.2f}s")

    if not result.detections:
        console.print("  [dim]No technologies detected[/]")
        return

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("Technology", style="cyan")
    table.add_column("Category", style="dim")
    table.add_column("Confidence", justify="right")
    table.add_column("Version", style="dim")

    for det in result.detections:
        conf = det["confidence"]
        conf_str = f"[green]{conf}[/]" if conf >= 80 else f"[yellow]{conf}[/]" if conf >= 60 else f"[red]{conf}[/]"
        table.add_row(det["tech"], det["category"], conf_str, det.get("version", ""))

    console.print(table)


def _print_batch_summary(results: list[CrawlResult]):
    ok = [r for r in results if not r.error]
    errors = [r for r in results if r.error]
    total_detections = sum(len(r.detections) for r in ok)
    avg_time = sum(r.crawl_time for r in ok) / len(ok) if ok else 0

    console.print(f"\n[bold]Batch Summary[/]")
    console.print(f"  Crawled: [green]{len(ok)}[/] ok, [red]{len(errors)}[/] errors")
    console.print(f"  Detections: {total_detections} technologies found")
    console.print(f"  Avg crawl time: {avg_time:.2f}s")
