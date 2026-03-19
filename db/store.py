import aiosqlite
import json
from pathlib import Path
from datetime import datetime
from config import DB_PATH

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db():
    schema = SCHEMA_PATH.read_text()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(schema)
        await db.commit()


# ── Sites ────────────────────────────────────────────────────────────────────

async def upsert_site(db: aiosqlite.Connection, domain: str, tier: int = 3) -> int:
    await db.execute(
        """INSERT INTO sites (domain, crawl_tier) VALUES (?, ?)
           ON CONFLICT(domain) DO NOTHING""",
        (domain, tier),
    )
    await db.commit()
    async with db.execute("SELECT id FROM sites WHERE domain = ?", (domain,)) as cur:
        row = await cur.fetchone()
    return row["id"]


async def update_site_crawled(db: aiosqlite.Connection, domain: str, status_code: int):
    new_status = "active" if status_code and 200 <= status_code < 400 else "error"
    await db.execute(
        """UPDATE sites SET last_crawled = datetime('now'), last_status_code = ?, status = ?
           WHERE domain = ?""",
        (status_code, new_status, domain),
    )
    await db.commit()


async def get_site_stats(db: aiosqlite.Connection, domain: str) -> dict | None:
    async with db.execute(
        """SELECT s.domain, s.last_crawled, s.crawl_tier, s.last_status_code,
                  COUNT(st.tech_id) as tech_count
           FROM sites s
           LEFT JOIN site_technologies st ON st.site_id = s.id
           WHERE s.domain = ?
           GROUP BY s.id""",
        (domain,),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


# ── Technologies ─────────────────────────────────────────────────────────────

async def get_or_create_tech(db: aiosqlite.Connection, name: str, category: str, website: str = "") -> int:
    await db.execute(
        """INSERT INTO technologies (name, category, website) VALUES (?, ?, ?)
           ON CONFLICT(name) DO NOTHING""",
        (name, category, website),
    )
    await db.commit()
    async with db.execute("SELECT id FROM technologies WHERE name = ?", (name,)) as cur:
        row = await cur.fetchone()
    return row["id"]


# ── Site Technologies ─────────────────────────────────────────────────────────

async def save_detections(db: aiosqlite.Connection, site_id: int, detections: list[dict]):
    """Upsert detected technologies and record changes."""
    # Fetch existing techs for this site
    async with db.execute(
        "SELECT tech_id, confidence, version FROM site_technologies WHERE site_id = ?",
        (site_id,),
    ) as cur:
        existing = {row["tech_id"]: dict(row) async for row in cur}

    for det in detections:
        tech_id = await get_or_create_tech(db, det["tech"], det["category"], det.get("website", ""))

        if tech_id in existing:
            old = existing[tech_id]
            if old["version"] != det.get("version"):
                await _record_change(db, site_id, tech_id, "version_change", old["version"], det.get("version"))
            await db.execute(
                """UPDATE site_technologies SET confidence = ?, version = ?, last_seen = datetime('now')
                   WHERE site_id = ? AND tech_id = ?""",
                (det["confidence"], det.get("version"), site_id, tech_id),
            )
        else:
            await db.execute(
                """INSERT INTO site_technologies (site_id, tech_id, confidence, version)
                   VALUES (?, ?, ?, ?)""",
                (site_id, tech_id, det["confidence"], det.get("version")),
            )
            await _record_change(db, site_id, tech_id, "added", None, det.get("version"))

    # Check for removed techs
    detected_ids = set()
    for det in detections:
        async with db.execute("SELECT id FROM technologies WHERE name = ?", (det["tech"],)) as cur:
            row = await cur.fetchone()
            if row:
                detected_ids.add(row["id"])

    for tech_id in existing:
        if tech_id not in detected_ids:
            await _record_change(db, site_id, tech_id, "removed", existing[tech_id]["version"], None)

    await db.commit()


async def _record_change(db, site_id, tech_id, change_type, old_version, new_version):
    await db.execute(
        """INSERT INTO tech_changes (site_id, tech_id, change_type, old_version, new_version)
           VALUES (?, ?, ?, ?, ?)""",
        (site_id, tech_id, change_type, old_version, new_version),
    )


# ── Crawl Jobs ───────────────────────────────────────────────────────────────

async def enqueue_job(db: aiosqlite.Connection, domain: str, priority: int = 5, reason: str = ""):
    await db.execute(
        """INSERT INTO crawl_jobs (domain, priority, reason) VALUES (?, ?, ?)""",
        (domain, priority, reason),
    )
    await db.commit()


async def get_pending_jobs(db: aiosqlite.Connection, limit: int = 50) -> list[dict]:
    async with db.execute(
        """SELECT * FROM crawl_jobs WHERE status = 'queued'
           ORDER BY priority DESC, created_at ASC LIMIT ?""",
        (limit,),
    ) as cur:
        return [dict(row) async for row in cur]


async def update_job_status(db: aiosqlite.Connection, job_id: int, status: str, error: str = ""):
    now = datetime.utcnow().isoformat()
    if status == "running":
        await db.execute(
            "UPDATE crawl_jobs SET status = ?, started_at = ? WHERE id = ?",
            (status, now, job_id),
        )
    else:
        await db.execute(
            "UPDATE crawl_jobs SET status = ?, completed_at = ?, error_message = ? WHERE id = ?",
            (status, now, error, job_id),
        )
    await db.commit()


async def get_queue_stats(db: aiosqlite.Connection) -> dict:
    async with db.execute(
        "SELECT status, COUNT(*) as cnt FROM crawl_jobs GROUP BY status"
    ) as cur:
        return {row["status"]: row["cnt"] async for row in cur}


# ── Unknown Signals ───────────────────────────────────────────────────────────

async def record_unknown_signal(db: aiosqlite.Connection, signal_type: str, signal_value: str, domain: str):
    await db.execute(
        """INSERT INTO unknown_signals (signal_type, signal_value, domain, count)
           VALUES (?, ?, ?, 1)
           ON CONFLICT(signal_type, signal_value)
           DO UPDATE SET count = count + 1, domain = excluded.domain""",
        (signal_type, signal_value, domain),
    )
    await db.commit()


async def get_unknown_signals(db: aiosqlite.Connection, min_count: int = 3, limit: int = 50) -> list[dict]:
    async with db.execute(
        """SELECT * FROM unknown_signals WHERE processed = 0 AND count >= ?
           ORDER BY count DESC LIMIT ?""",
        (min_count, limit),
    ) as cur:
        return [dict(row) async for row in cur]


async def get_stats(db: aiosqlite.Connection) -> dict:
    stats = {}
    async with db.execute("SELECT COUNT(*) as cnt FROM sites") as cur:
        stats["total_sites"] = (await cur.fetchone())["cnt"]
    async with db.execute("SELECT COUNT(*) as cnt FROM technologies") as cur:
        stats["total_technologies"] = (await cur.fetchone())["cnt"]
    async with db.execute("SELECT COUNT(*) as cnt FROM tech_changes WHERE detected_at > datetime('now', '-24 hours')") as cur:
        stats["changes_24h"] = (await cur.fetchone())["cnt"]
    queue = await get_queue_stats(db)
    stats["queue"] = queue
    return stats
