"""
Lead Generation Agent: translates natural language technology queries into
filtered site lists for sales prospecting, exports as CSV or JSON.
"""
import asyncio
import csv
import json
from datetime import datetime
from pathlib import Path

import anthropic
import aiosqlite
from rich.console import Console
from rich.table import Table

from config import ANTHROPIC_API_KEY, MODEL
from db.store import get_db

console = Console()

# ── Tool implementations ────────────────────────────────────────────────────

async def _list_technologies(db: aiosqlite.Connection, category: str = None) -> list:
    if category:
        cur = await db.execute(
            "SELECT name, category FROM technologies WHERE LOWER(category) LIKE LOWER(?) ORDER BY category, name",
            (f"%{category}%",),
        )
    else:
        cur = await db.execute(
            "SELECT name, category FROM technologies ORDER BY category, name"
        )
    rows = await cur.fetchall()
    return [{"name": r[0], "category": r[1]} for r in rows]


async def _query_sites(
    db: aiosqlite.Connection,
    must_have: list = None,
    must_not_have: list = None,
    any_of: list = None,
    category_filter: str = None,
    limit: int = 200,
) -> list:
    must_have = must_have or []
    must_not_have = must_not_have or []
    any_of = any_of or []
    limit = min(limit, 500)

    query = "SELECT s.id, s.domain FROM sites s WHERE s.status = 'active'"
    params = []

    for tech in must_have:
        query += """
            AND EXISTS (
                SELECT 1 FROM site_technologies st
                JOIN technologies t ON st.tech_id = t.id
                WHERE st.site_id = s.id AND LOWER(t.name) = LOWER(?)
            )"""
        params.append(tech)

    for tech in must_not_have:
        query += """
            AND NOT EXISTS (
                SELECT 1 FROM site_technologies st
                JOIN technologies t ON st.tech_id = t.id
                WHERE st.site_id = s.id AND LOWER(t.name) = LOWER(?)
            )"""
        params.append(tech)

    if any_of:
        placeholders = ",".join("LOWER(?)" for _ in any_of)
        query += f"""
            AND EXISTS (
                SELECT 1 FROM site_technologies st
                JOIN technologies t ON st.tech_id = t.id
                WHERE st.site_id = s.id AND LOWER(t.name) IN ({placeholders})
            )"""
        params.extend(any_of)

    if category_filter:
        query += """
            AND EXISTS (
                SELECT 1 FROM site_technologies st
                JOIN technologies t ON st.tech_id = t.id
                WHERE st.site_id = s.id AND LOWER(t.category) LIKE LOWER(?)
            )"""
        params.append(f"%{category_filter}%")

    query += " ORDER BY s.domain LIMIT ?"
    params.append(limit)

    cur = await db.execute(query, params)
    site_rows = await cur.fetchall()

    results = []
    for site_id, domain in site_rows:
        cur2 = await db.execute(
            """SELECT t.name, t.category, st.confidence
               FROM site_technologies st
               JOIN technologies t ON st.tech_id = t.id
               WHERE st.site_id = ?
               ORDER BY st.confidence DESC""",
            (site_id,),
        )
        techs = [{"name": r[0], "category": r[1], "confidence": r[2]} for r in await cur2.fetchall()]
        results.append({"domain": domain, "tech_count": len(techs), "technologies": techs})

    return results


async def _get_site_details(db: aiosqlite.Connection, domain: str) -> dict:
    cur = await db.execute(
        "SELECT id, status, last_crawled FROM sites WHERE domain = ?", (domain,)
    )
    site = await cur.fetchone()
    if not site:
        return {"error": f"Domain '{domain}' not found in database"}
    cur2 = await db.execute(
        """SELECT t.name, t.category, st.confidence, st.version
           FROM site_technologies st
           JOIN technologies t ON st.tech_id = t.id
           WHERE st.site_id = ?
           ORDER BY st.confidence DESC""",
        (site[0],),
    )
    techs = [{"name": r[0], "category": r[1], "confidence": r[2], "version": r[3]} for r in await cur2.fetchall()]
    return {"domain": domain, "status": site[1], "last_crawled": site[2], "technologies": techs}


async def _get_market_overview(db: aiosqlite.Connection, category: str = None) -> dict:
    total_cur = await db.execute("SELECT COUNT(*) FROM sites WHERE status = 'active'")
    total = (await total_cur.fetchone())[0]

    if category:
        cur = await db.execute(
            """SELECT t.name, COUNT(DISTINCT st.site_id) as sites
               FROM site_technologies st JOIN technologies t ON st.tech_id = t.id
               WHERE LOWER(t.category) LIKE LOWER(?)
               GROUP BY t.id ORDER BY sites DESC LIMIT 20""",
            (f"%{category}%",),
        )
        rows = await cur.fetchall()
        tech_stats = [{"name": r[0], "sites": r[1], "penetration_pct": round(r[1] / total * 100, 1)} for r in rows]
    else:
        cur = await db.execute(
            """SELECT t.name, t.category, COUNT(DISTINCT st.site_id) as sites
               FROM site_technologies st JOIN technologies t ON st.tech_id = t.id
               GROUP BY t.id ORDER BY sites DESC LIMIT 30"""
        )
        rows = await cur.fetchall()
        tech_stats = [{"name": r[0], "category": r[1], "sites": r[2], "penetration_pct": round(r[2] / total * 100, 1)} for r in rows]

    return {"total_active_sites": total, "technologies": tech_stats}


def _export_leads(sites: list, fmt: str = "csv", filename: str = None) -> dict:
    output_dir = Path("exports")
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"{filename or 'leads'}_{timestamp}.{fmt}"
    filepath = output_dir / fname

    if fmt == "json":
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(sites, f, indent=2, ensure_ascii=False)
    else:
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["domain", "tech_count", "technologies"])
            for site in sites:
                techs_str = ", ".join(t["name"] for t in site["technologies"])
                writer.writerow([site["domain"], site["tech_count"], techs_str])

    return {"filepath": str(filepath), "count": len(sites), "format": fmt}


def _print_results(sites: list, query: str):
    if not sites:
        console.print("[yellow]No matching sites found.[/]")
        return
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("Domain", style="cyan", min_width=30)
    table.add_column("Techs", justify="right", style="dim")
    table.add_column("Key Technologies", style="white")

    for site in sites[:50]:
        top = ", ".join(t["name"] for t in site["technologies"][:5])
        table.add_row(site["domain"], str(site["tech_count"]), top)

    if len(sites) > 50:
        console.print(f"[dim]Showing 50 of {len(sites)} results[/]")
    console.print(table)


# ── Tool definitions ────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "list_technologies",
        "description": (
            "List all technologies available in the database with their categories. "
            "Call this first to find exact technology names before querying. "
            "Optionally filter by category (e.g. 'CMS', 'Analytics', 'CDN', 'JavaScript Framework')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Optional partial category name to filter (e.g. 'cms', 'analytics')",
                }
            },
            "required": [],
        },
    },
    {
        "name": "query_sites",
        "description": (
            "Query sites matching technology criteria. Returns domains with full tech stacks. "
            "must_have = site has ALL these (AND). must_not_have = site has NONE of these. "
            "any_of = site has AT LEAST ONE (OR). Use exact names from list_technologies."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "must_have": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "ALL of these techs must be present on the site.",
                },
                "must_not_have": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "NONE of these techs must be present on the site.",
                },
                "any_of": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "AT LEAST ONE of these techs must be present (OR logic).",
                },
                "category_filter": {
                    "type": "string",
                    "description": "Only include sites with at least one tech in this category.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default 200, max 500).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_site_details",
        "description": "Get the complete technology stack for a specific domain.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Domain to look up (e.g. 'shopify.com')"}
            },
            "required": ["domain"],
        },
    },
    {
        "name": "get_market_overview",
        "description": "Aggregate market stats: top technologies by site count and penetration %. Optionally filter by category.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Optional category to focus on (e.g. 'Analytics', 'CMS')",
                }
            },
            "required": [],
        },
    },
    {
        "name": "export_leads",
        "description": "Export the results from the most recent query_sites call to a file. Call this after query_sites.",
        "input_schema": {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "enum": ["csv", "json"],
                    "description": "Export format: 'csv' (default) or 'json'",
                },
                "filename": {
                    "type": "string",
                    "description": "Optional filename prefix (without extension)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "finish_query",
        "description": "Signal completion. Call this when you have found and exported the leads.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Brief summary: how many leads found, what filters were applied, export path.",
                },
                "lead_count": {"type": "integer", "description": "Number of leads found"},
                "export_path": {"type": "string", "description": "Path to the exported file"},
            },
            "required": ["summary", "lead_count"],
        },
    },
]

SYSTEM_PROMPT = """You are a lead generation specialist with access to a web technology intelligence database.
Your job: translate the user's natural language query into precise technology filters, find matching sites, and export results.

Workflow:
1. Call list_technologies() to find exact tech names (spelling matters for filters)
2. Call query_sites() with appropriate must_have / must_not_have / any_of / category_filter
3. Call export_leads() to save results to file
4. Call finish_query() with a brief summary

Rules:
- Always verify exact tech names via list_technologies before querying
- Be precise: if the user says "no analytics", use must_not_have for specific analytics tools
- Export is always the last step before finish_query
"""

# ── Agent loop ──────────────────────────────────────────────────────────────

async def run_lead_agent(query: str, export_fmt: str = "csv") -> dict:
    """Run the Lead Generation Agent with a natural language query."""
    console.print(f"\n[bold magenta]Lead Generation Agent[/]")
    console.print(f'  Query: [italic]"{query}"[/]\n')

    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY, max_retries=4)
    db = await get_db()
    messages = [{"role": "user", "content": f"{query}\n\nExport format: {export_fmt}"}]

    stored_sites = []
    result = {"lead_count": 0, "export_path": None, "summary": ""}
    done = False

    try:
        while not done:
            response = await client.messages.create(
                model=MODEL,
                max_tokens=4096,
                thinking={"type": "adaptive"},
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )

            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                text = " ".join(b.text for b in response.content if b.type == "text")
                result["summary"] = text
                break

            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                name = block.name
                inp = block.input
                console.print(f"  [dim]-> {name}({json.dumps(inp, ensure_ascii=False)[:100]})[/]")

                try:
                    if name == "list_technologies":
                        out = await _list_technologies(db, inp.get("category"))

                    elif name == "query_sites":
                        out = await _query_sites(
                            db,
                            must_have=inp.get("must_have", []),
                            must_not_have=inp.get("must_not_have", []),
                            any_of=inp.get("any_of", []),
                            category_filter=inp.get("category_filter"),
                            limit=inp.get("limit", 200),
                        )
                        stored_sites = out
                        console.print(f"     [green]Found {len(out)} matching sites[/]")
                        _print_results(out, query)

                    elif name == "get_site_details":
                        out = await _get_site_details(db, inp["domain"])

                    elif name == "get_market_overview":
                        out = await _get_market_overview(db, inp.get("category"))

                    elif name == "export_leads":
                        out = _export_leads(
                            stored_sites,
                            fmt=inp.get("format", export_fmt),
                            filename=inp.get("filename"),
                        )
                        result["export_path"] = out["filepath"]
                        console.print(f"     [green]Exported {out['count']} leads -> {out['filepath']}[/]")

                    elif name == "finish_query":
                        result["lead_count"] = inp.get("lead_count", len(stored_sites))
                        result["summary"] = inp.get("summary", "")
                        if inp.get("export_path"):
                            result["export_path"] = inp["export_path"]
                        out = {"status": "done"}
                        done = True

                    else:
                        out = {"error": f"Unknown tool: {name}"}

                except Exception as e:
                    out = {"error": str(e)}

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(out, ensure_ascii=False),
                })

            if tool_results:
                messages.append({"role": "user", "content": tool_results})

    finally:
        await db.close()

    return result
