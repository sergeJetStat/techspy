"""
Detection Agent — Claude opus-4-6 agentic loop.

Researches unknown signals and proposes new fingerprint rules.
Tools: search_similar_domains, propose_fingerprint, save_fingerprint_draft
"""
import json
import asyncio
import anthropic
import aiosqlite
from pathlib import Path
from rich.console import Console
from config import MODEL, MAX_TOKENS
from db.store import get_db, get_unknown_signals
from detection.engine import get_tech_db

console = Console()

FINGERPRINT_DRAFTS_PATH = Path("fingerprint_drafts.json")

SYSTEM_PROMPT = """You are the Detection Agent for a web technology intelligence platform.

Your job is to investigate unknown signals (script URLs, HTTP headers, JS globals) found during crawling
and propose new fingerprint rules for technologies not yet in our database.

When given unknown signals, you should:
1. Use search_similar_domains to see which sites share this signal
2. Identify the technology based on the signal pattern (URL path, header value, etc.)
3. Research what the technology is (CMS, analytics tool, payment processor, etc.)
4. Propose a complete fingerprint rule using propose_fingerprint
5. Save promising fingerprints for human review using save_fingerprint_draft

Fingerprint format:
{
  "name": "TechName",
  "categories": ["Category"],
  "website": "https://example.com",
  "implies": [],
  "patterns": {
    "html": ["pattern1", "pattern2"],
    "headers": {"Header-Name": "pattern"},
    "meta_generator": "pattern",
    "cookies": ["prefix_"],
    "scripts": ["path/pattern"]
  }
}

Only propose fingerprints you are confident about. Leave patterns empty if uncertain.
Call finish_review when done with the current batch."""

TOOLS = [
    {
        "name": "search_similar_domains",
        "description": "Find other domains that share the same unknown signal.",
        "input_schema": {
            "type": "object",
            "properties": {
                "signal_type": {"type": "string", "description": "Type: 'script_src', 'header', 'cookie', 'html'"},
                "signal_value": {"type": "string", "description": "The signal value to search for"}
            },
            "required": ["signal_type", "signal_value"]
        }
    },
    {
        "name": "get_signal_details",
        "description": "Get details about an unknown signal including count and example domains.",
        "input_schema": {
            "type": "object",
            "properties": {
                "signal_value": {"type": "string"}
            },
            "required": ["signal_value"]
        }
    },
    {
        "name": "propose_fingerprint",
        "description": "Propose a new technology fingerprint based on discovered signals.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fingerprint": {
                    "type": "object",
                    "description": "The fingerprint object following the standard format"
                },
                "confidence": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": "How confident you are in this fingerprint"
                },
                "reasoning": {
                    "type": "string",
                    "description": "Explanation of how you identified this technology"
                }
            },
            "required": ["fingerprint", "confidence", "reasoning"]
        }
    },
    {
        "name": "save_fingerprint_draft",
        "description": "Save a proposed fingerprint to the drafts file for human review.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tech_name": {"type": "string"},
                "fingerprint": {"type": "object"},
                "confidence": {"type": "string"},
                "reasoning": {"type": "string"}
            },
            "required": ["tech_name", "fingerprint", "confidence", "reasoning"]
        }
    },
    {
        "name": "finish_review",
        "description": "Signal that all signals in the current batch have been reviewed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Summary: how many fingerprints proposed, key findings"}
            },
            "required": ["summary"]
        }
    }
]


async def _execute_tool(tool_name: str, tool_input: dict, db: aiosqlite.Connection, proposed: list) -> str:
    if tool_name == "search_similar_domains":
        signal_value = tool_input.get("signal_value", "")
        async with db.execute(
            """SELECT domain, count FROM unknown_signals
               WHERE signal_value LIKE ? ORDER BY count DESC LIMIT 10""",
            (f"%{signal_value[:50]}%",),
        ) as cur:
            rows = [dict(r) async for r in cur]
        return json.dumps({"matches": rows, "total": len(rows)})

    elif tool_name == "get_signal_details":
        signal_value = tool_input.get("signal_value", "")
        async with db.execute(
            """SELECT signal_type, signal_value, domain, count, created_at
               FROM unknown_signals WHERE signal_value LIKE ? LIMIT 5""",
            (f"%{signal_value[:50]}%",),
        ) as cur:
            rows = [dict(r) async for r in cur]
        return json.dumps(rows)

    elif tool_name == "propose_fingerprint":
        fp = tool_input.get("fingerprint", {})
        confidence = tool_input.get("confidence", "low")
        reasoning = tool_input.get("reasoning", "")
        proposed.append({
            "tech_name": fp.get("name", "Unknown"),
            "fingerprint": fp,
            "confidence": confidence,
            "reasoning": reasoning,
        })
        console.print(f"  [yellow]-> Proposed:[/] {fp.get('name', '?')} [{confidence}]")
        return json.dumps({"status": "proposed", "tech_name": fp.get("name")})

    elif tool_name == "save_fingerprint_draft":
        tech_name = tool_input.get("tech_name", "Unknown")
        draft = {
            "tech_name": tech_name,
            "fingerprint": tool_input.get("fingerprint", {}),
            "confidence": tool_input.get("confidence", "low"),
            "reasoning": tool_input.get("reasoning", ""),
        }

        existing = []
        if FINGERPRINT_DRAFTS_PATH.exists():
            try:
                existing = json.loads(FINGERPRINT_DRAFTS_PATH.read_text())
            except Exception:
                existing = []

        existing.append(draft)
        FINGERPRINT_DRAFTS_PATH.write_text(json.dumps(existing, indent=2, ensure_ascii=False))
        console.print(f"  [green]OK Saved draft:[/] {tech_name}")
        return json.dumps({"status": "saved", "tech_name": tech_name})

    elif tool_name == "finish_review":
        return json.dumps({"status": "done", "summary": tool_input.get("summary", "")})

    return json.dumps({"error": f"Unknown tool: {tool_name}"})


async def run_detection_agent(min_signal_count: int = 3) -> str:
    """
    Run the detection agent on accumulated unknown signals.
    Returns summary of proposed fingerprints.
    """
    db = await get_db()
    signals = await get_unknown_signals(db, min_count=min_signal_count, limit=10)

    if not signals:
        await db.close()
        return "No unknown signals to process."

    console.print(f"[bold magenta]Detection Agent[/] - analyzing {len(signals)} unknown signals")

    client = anthropic.AsyncAnthropic(max_retries=8)
    proposed: list[dict] = []

    signal_list = json.dumps(signals, indent=2)
    user_message = (
        f"Investigate these {len(signals)} unknown signals found during web crawling "
        f"and identify if they belong to any technology we should fingerprint:\n\n{signal_list}"
    )

    messages = [{"role": "user", "content": user_message}]
    summary = "No summary provided."
    done = False

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

            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                break

            if response.stop_reason == "tool_use":
                tool_results = []

                for block in response.content:
                    if block.type == "tool_use":
                        console.print(f"  [dim]-> {block.name}[/]")
                        result = await _execute_tool(block.name, block.input, db, proposed)

                        if block.name == "finish_review":
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

        # Mark processed signals
        if proposed:
            await db.execute(
                "UPDATE unknown_signals SET processed = 1 WHERE processed = 0 AND count >= ?",
                (min_signal_count,),
            )
            await db.commit()

    finally:
        await db.close()

    safe_summary = summary.encode("ascii", "replace").decode("ascii")
    console.print(f"[green]OK Detection Agent done:[/] {safe_summary}")
    console.print(f"  Proposed {len(proposed)} fingerprints. Check [bold]fingerprint_drafts.json[/] for review.")
    return summary
