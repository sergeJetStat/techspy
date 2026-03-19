"""
Crawl Scheduler Agent — Claude opus-4-6 agentic loop.

Decides which domains to crawl, sets priorities and frequencies.
Tools: get_domain_stats, get_queue_stats, schedule_crawl, set_crawl_frequency
"""
import json
import asyncio
import anthropic
import aiosqlite
from rich.console import Console
from config import MODEL, MAX_TOKENS
from db.store import get_db, get_site_stats, get_queue_stats, enqueue_job, upsert_site

console = Console()

SYSTEM_PROMPT = """You are the Crawl Scheduler for a web technology intelligence platform (like BuiltWith).

Your job is to analyze domain request queues and decide:
1. Which domains to crawl and with what priority (1=low, 10=urgent)
2. How frequently to crawl each domain (crawl tier: 1=weekly, 2=biweekly, 3=monthly)
3. Why each crawl is needed (reason string for the job)

Priority guidelines:
- New domain never crawled: priority 8
- High-traffic domain (tier 1): priority 6
- Domain with recent activity: priority 7
- Routine recrawl: priority 3-4
- Manual user request: priority 10

Use tools to check current stats before scheduling. Schedule efficiently — don't queue duplicates.
When done, call end_scheduling to finish."""

TOOLS = [
    {
        "name": "get_domain_stats",
        "description": "Get crawl history and tech stack info for a domain from the database.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "The domain to look up (e.g. 'example.com')"}
            },
            "required": ["domain"]
        }
    },
    {
        "name": "get_queue_stats",
        "description": "Get current crawl queue statistics (queued, running, done, error counts).",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "schedule_crawl",
        "description": "Add a domain to the crawl queue with a given priority and reason.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Domain to crawl (e.g. 'github.com')"},
                "priority": {"type": "integer", "description": "Priority 1-10 (10=urgent)", "minimum": 1, "maximum": 10},
                "reason": {"type": "string", "description": "Why this crawl is scheduled"}
            },
            "required": ["domain", "priority", "reason"]
        }
    },
    {
        "name": "set_crawl_frequency",
        "description": "Set the crawl tier (frequency) for a domain.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string"},
                "tier": {"type": "integer", "description": "1=weekly, 2=biweekly, 3=monthly", "minimum": 1, "maximum": 3}
            },
            "required": ["domain", "tier"]
        }
    },
    {
        "name": "end_scheduling",
        "description": "Signal that scheduling is complete for the current batch.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Brief summary of what was scheduled"}
            },
            "required": ["summary"]
        }
    }
]


async def _execute_tool(tool_name: str, tool_input: dict, db: aiosqlite.Connection) -> str:
    if tool_name == "get_domain_stats":
        stats = await get_site_stats(db, tool_input["domain"])
        if stats:
            return json.dumps(stats)
        return json.dumps({"domain": tool_input["domain"], "status": "never_crawled"})

    elif tool_name == "get_queue_stats":
        stats = await get_queue_stats(db)
        return json.dumps(stats)

    elif tool_name == "schedule_crawl":
        domain = tool_input["domain"]
        priority = tool_input["priority"]
        reason = tool_input.get("reason", "")
        await upsert_site(db, domain)
        job_id = await enqueue_job(db, domain, priority, reason)
        return json.dumps({"status": "queued", "job_id": job_id, "domain": domain})

    elif tool_name == "set_crawl_frequency":
        domain = tool_input["domain"]
        tier = tool_input["tier"]
        await db.execute(
            "UPDATE sites SET crawl_tier = ? WHERE domain = ?",
            (tier, domain)
        )
        await db.commit()
        return json.dumps({"status": "updated", "domain": domain, "tier": tier})

    elif tool_name == "end_scheduling":
        return json.dumps({"status": "done", "summary": tool_input.get("summary", "")})

    return json.dumps({"error": f"Unknown tool: {tool_name}"})


async def run_crawl_scheduler(domains: list[str]) -> str:
    """
    Run the crawl scheduler agent for a batch of domains.
    Returns a summary of what was scheduled.
    """
    client = anthropic.AsyncAnthropic()
    db = await get_db()

    domain_list = ", ".join(domains) if len(domains) <= 10 else f"{len(domains)} domains"
    user_message = f"Schedule crawls for these domains: {domain_list}\n\nDomains: {json.dumps(domains)}"

    messages = [{"role": "user", "content": user_message}]
    summary = "No summary provided."
    done = False

    console.print(f"[bold cyan]Crawl Scheduler Agent[/] — scheduling {len(domains)} domains")

    try:
        while not done:
            response = await client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                thinking={"type": "adaptive"},
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )

            # Append assistant response to history
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                break

            if response.stop_reason == "tool_use":
                tool_results = []

                for block in response.content:
                    if block.type == "tool_use":
                        console.print(f"  [dim]-> {block.name}({json.dumps(block.input, ensure_ascii=False)[:80]})[/]")

                        result = await _execute_tool(block.name, block.input, db)

                        if block.name == "end_scheduling":
                            result_data = json.loads(result)
                            summary = result_data.get("summary", summary)
                            done = True

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })

                messages.append({"role": "user", "content": tool_results})

                if done:
                    break

    finally:
        await db.close()

    console.print(f"[green]OK Scheduler done:[/] {summary}")
    return summary
