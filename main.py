#!/usr/bin/env python3
"""
TechSpy CLI — web technology intelligence platform.

Usage:
  python main.py crawl shopify.com
  python main.py crawl-batch domains.txt --concurrency 20
  python main.py scheduler domains.txt
  python main.py detect-unknown
  python main.py stats
  python main.py leads "Shopify sites without Google Analytics"
"""
import asyncio
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from db.store import init_db, get_db, get_stats

console = Console()


def run(coro):
    """Run an async function from sync context."""
    return asyncio.run(coro)


@click.group()
def cli():
    """TechSpy — web technology intelligence."""
    pass


@cli.command()
@click.argument("domain")
@click.option("--no-scheduler", is_flag=True, help="Skip the Crawl Scheduler agent")
def crawl(domain: str, no_scheduler: bool):
    """Crawl a single domain and detect technologies."""
    async def _run():
        await init_db()
        from pipeline import crawl_and_store
        await crawl_and_store(domain, verbose=True)

    run(_run())


@cli.command("crawl-batch")
@click.argument("file", type=click.Path(exists=True))
@click.option("--concurrency", default=20, show_default=True, help="Max concurrent crawls")
@click.option("--no-scheduler", is_flag=True, help="Skip Crawl Scheduler agent")
def crawl_batch(file: str, concurrency: int, no_scheduler: bool):
    """Crawl multiple domains from a file (one domain per line)."""
    domains = [
        line.strip()
        for line in Path(file).read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]

    if not domains:
        console.print("[red]No domains found in file.[/]")
        sys.exit(1)

    console.print(f"Loaded [bold]{len(domains)}[/] domains from [cyan]{file}[/]")

    async def _run():
        import config
        config.MAX_CONCURRENT_CRAWLS = concurrency
        from pipeline import crawl_batch as _batch
        await _batch(domains, use_scheduler=not no_scheduler)

    run(_run())


@cli.command()
@click.argument("file", type=click.Path(exists=True))
def scheduler(file: str):
    """Run Crawl Scheduler agent on domains from a file."""
    domains = [
        line.strip()
        for line in Path(file).read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]

    async def _run():
        await init_db()
        from agents.crawl_scheduler import run_crawl_scheduler
        summary = await run_crawl_scheduler(domains)
        console.print(f"\n[bold]Scheduler summary:[/] {summary}")

    run(_run())


@cli.command("detect-unknown")
@click.option("--min-count", default=3, show_default=True, help="Minimum signal occurrences to investigate")
def detect_unknown(min_count: int):
    """Run Detection Agent to investigate unknown signals."""
    async def _run():
        await init_db()
        from agents.detection_agent import run_detection_agent
        summary = await run_detection_agent(min_signal_count=min_count)
        console.print(f"\n[bold]Detection summary:[/] {summary}")

    run(_run())


@cli.command()
def stats():
    """Show database and queue statistics."""
    async def _run():
        await init_db()
        db = await get_db()
        try:
            s = await get_stats(db)
        finally:
            await db.close()

        console.print("\n[bold]TechSpy Statistics[/]\n")

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Metric", style="dim")
        table.add_column("Value", style="bold cyan")

        table.add_row("Total sites", str(s.get("total_sites", 0)))
        table.add_row("Technologies tracked", str(s.get("total_technologies", 0)))
        table.add_row("Tech changes (24h)", str(s.get("changes_24h", 0)))

        queue = s.get("queue", {})
        table.add_row("Queue: queued", str(queue.get("queued", 0)))
        table.add_row("Queue: running", str(queue.get("running", 0)))
        table.add_row("Queue: done", str(queue.get("done", 0)))
        table.add_row("Queue: error", str(queue.get("error", 0)))

        console.print(table)

    run(_run())


@cli.command()
@click.argument("domain")
def lookup(domain: str):
    """Look up detected technologies for a domain (from DB)."""
    async def _run():
        await init_db()
        db = await get_db()
        try:
            import aiosqlite
            async with db.execute(
                """SELECT t.name, t.category, st.confidence, st.version, st.last_seen
                   FROM site_technologies st
                   JOIN technologies t ON t.id = st.tech_id
                   JOIN sites s ON s.id = st.site_id
                   WHERE s.domain = ?
                   ORDER BY st.confidence DESC""",
                (domain,),
            ) as cur:
                rows = [dict(r) async for r in cur]
        finally:
            await db.close()

        if not rows:
            console.print(f"[yellow]No data for {domain}. Run:[/] python main.py crawl {domain}")
            return

        console.print(f"\n[bold]{domain}[/] — {len(rows)} technologies detected\n")
        table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
        table.add_column("Technology", style="cyan")
        table.add_column("Category", style="dim")
        table.add_column("Confidence", justify="right")
        table.add_column("Version", style="dim")
        table.add_column("Last seen", style="dim")

        for row in rows:
            conf = row["confidence"]
            conf_str = (
                f"[green]{conf}[/]" if conf >= 80
                else f"[yellow]{conf}[/]" if conf >= 60
                else f"[red]{conf}[/]"
            )
            table.add_row(
                row["name"], row["category"], conf_str,
                row.get("version") or "", row.get("last_seen", "")[:10]
            )

        console.print(table)

    run(_run())


@cli.command()
@click.argument("query")
@click.option("--format", "fmt", default="csv", type=click.Choice(["csv", "json"]), help="Export format")
def leads(query: str, fmt: str):
    """Generate leads from a natural language technology query.

    \b
    Examples:
      py main.py leads "sites using WordPress"
      py main.py leads "Shopify sites without Google Analytics"
      py main.py leads "Next.js sites on Vercel" --format json
      py main.py leads "Bootstrap sites without jQuery"
    """
    from config import ANTHROPIC_API_KEY
    if not ANTHROPIC_API_KEY:
        console.print("[red]Error: ANTHROPIC_API_KEY not set in .env[/]")
        return

    async def _run():
        await init_db()
        from agents.lead_agent import run_lead_agent
        result = await run_lead_agent(query, export_fmt=fmt)
        if result.get("summary"):
            safe = result["summary"].encode("ascii", "replace").decode("ascii")
            console.print(f"\n[bold]Summary:[/] {safe}")
        console.print(f"[bold green]Leads found: {result['lead_count']}[/]")
        if result.get("export_path"):
            console.print(f"[dim]Exported to: {result['export_path']}[/]")

    run(_run())


if __name__ == "__main__":
    cli()
