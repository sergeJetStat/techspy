"""TechSpy web server — FastAPI backend serving the UI and database API."""
from __future__ import annotations

import asyncio
import csv
import io
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

DB_PATH = os.getenv("DB_PATH", str(Path(__file__).parent / "techspy.db"))
WEBSITE_DIR = Path(__file__).parent / "website"

# How many domains to crawl per background batch
CRAWL_BATCH_SIZE = int(os.getenv("CRAWL_BATCH_SIZE", "10"))
# Seconds between crawl batches
CRAWL_INTERVAL = int(os.getenv("CRAWL_INTERVAL", "60"))
# Enable background crawling (set CRAWL_ENABLED=0 to disable)
CRAWL_ENABLED = os.getenv("CRAWL_ENABLED", "1") != "0"

log = logging.getLogger("techspy.server")


# ── Background crawler ────────────────────────────────────────────────────────

SEED_FILE = Path(__file__).parent / "domains1000.txt"


async def _seed_domains_if_empty():
    """On first run, populate sites table from domains1000.txt."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM sites")
        count = (await cur.fetchone())[0]
        if count > 0:
            return
        if not SEED_FILE.exists():
            return
        domains = [
            d.strip() for d in SEED_FILE.read_text().splitlines()
            if d.strip() and not d.startswith("#")
        ]
        for domain in domains:
            await db.execute(
                "INSERT INTO sites (domain) VALUES (?) ON CONFLICT(domain) DO NOTHING",
                (domain,),
            )
        await db.commit()
        log.info("Seeded %d domains from %s", len(domains), SEED_FILE.name)


async def _background_crawler():
    """Continuously pick stale sites and re-crawl them."""
    # Delay startup so the app can finish initialising
    await asyncio.sleep(10)

    # Import pipeline here to avoid circular-import issues at module load time
    from db.store import init_db
    from pipeline import crawl_and_store

    await init_db()
    await _seed_domains_if_empty()
    log.info("Background crawler started (batch=%d, interval=%ds)",
             CRAWL_BATCH_SIZE, CRAWL_INTERVAL)

    while True:
        try:
            # Pick sites not crawled in the last 24 h, oldest first
            async with aiosqlite.connect(DB_PATH) as db:
                cur = await db.execute(
                    """SELECT domain FROM sites
                       WHERE last_crawled IS NULL
                          OR last_crawled < datetime('now', '-24 hours')
                       ORDER BY last_crawled ASC NULLS FIRST
                       LIMIT ?""",
                    (CRAWL_BATCH_SIZE,),
                )
                rows = await cur.fetchall()

            domains = [r[0] for r in rows]
            if domains:
                log.info("Crawling %d stale domains…", len(domains))
                tasks = [crawl_and_store(d, verbose=False) for d in domains]
                await asyncio.gather(*tasks, return_exceptions=True)
                log.info("Batch done.")
            else:
                log.debug("No stale domains, sleeping.")

        except Exception as exc:
            log.exception("Background crawler error: %s", exc)

        await asyncio.sleep(CRAWL_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background tasks on startup."""
    task = None
    if CRAWL_ENABLED:
        task = asyncio.create_task(_background_crawler())
        log.info("Background crawl task created.")
    yield
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="TechSpy API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── helpers ───────────────────────────────────────────────────────────────────

async def _run_query(
    must_have: list[str],
    must_not_have: list[str],
    any_of: list[str],
    category: str,
    limit: int,
) -> list[dict]:
    q = "SELECT s.id, s.domain FROM sites s WHERE s.status = 'active'"
    p: list = []

    for t in must_have:
        q += (
            " AND EXISTS ("
            "SELECT 1 FROM site_technologies st"
            " JOIN technologies t ON st.tech_id = t.id"
            " WHERE st.site_id = s.id AND LOWER(t.name) = LOWER(?))"
        )
        p.append(t)

    for t in must_not_have:
        q += (
            " AND NOT EXISTS ("
            "SELECT 1 FROM site_technologies st"
            " JOIN technologies t ON st.tech_id = t.id"
            " WHERE st.site_id = s.id AND LOWER(t.name) = LOWER(?))"
        )
        p.append(t)

    if any_of:
        phs = ",".join("?" for _ in any_of)
        q += (
            f" AND EXISTS ("
            f"SELECT 1 FROM site_technologies st"
            f" JOIN technologies t ON st.tech_id = t.id"
            f" WHERE st.site_id = s.id AND LOWER(t.name) IN ({phs}))"
        )
        p.extend(t.lower() for t in any_of)

    if category:
        q += (
            " AND EXISTS ("
            "SELECT 1 FROM site_technologies st"
            " JOIN technologies t ON st.tech_id = t.id"
            " WHERE st.site_id = s.id AND LOWER(t.category) LIKE LOWER(?))"
        )
        p.append(f"%{category}%")

    q += " ORDER BY s.domain LIMIT ?"
    p.append(min(limit, 2000))

    results = []
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(q, p)
        rows = await cur.fetchall()
        for site_id, domain in rows:
            cur2 = await db.execute(
                "SELECT t.name, t.category, st.confidence"
                " FROM site_technologies st"
                " JOIN technologies t ON st.tech_id = t.id"
                " WHERE st.site_id = ? ORDER BY st.confidence DESC",
                (site_id,),
            )
            techs = [
                {"name": r[0], "category": r[1], "confidence": r[2]}
                for r in await cur2.fetchall()
            ]
            results.append({"domain": domain, "tech_count": len(techs), "technologies": techs})

    return results


# ── API routes ────────────────────────────────────────────────────────────────

@app.get("/api/stats")
async def get_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        sites = (await (await db.execute(
            "SELECT COUNT(*) FROM sites WHERE status='active'")).fetchone())[0]
        techs = (await (await db.execute(
            "SELECT COUNT(*) FROM technologies")).fetchone())[0]
        detections = (await (await db.execute(
            "SELECT COUNT(*) FROM site_technologies")).fetchone())[0]
        crawling = (await (await db.execute(
            "SELECT COUNT(*) FROM sites WHERE last_crawled IS NULL "
            "OR last_crawled < datetime('now', '-24 hours')")).fetchone())[0]
    return {
        "sites": sites,
        "technologies": techs,
        "detections": detections,
        "crawl_queue": crawling,
    }


@app.get("/api/technologies")
async def get_technologies():
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT name, category FROM technologies ORDER BY category, name"
        )
        rows = await cur.fetchall()
    return [{"name": r[0], "category": r[1]} for r in rows]


class SearchReq(BaseModel):
    must_have: list[str] = []
    must_not_have: list[str] = []
    any_of: list[str] = []
    category: str = ""
    limit: int = 200


@app.post("/api/search")
async def search(req: SearchReq):
    sites = await _run_query(
        req.must_have, req.must_not_have, req.any_of, req.category, req.limit
    )
    return {"count": len(sites), "sites": sites}


@app.get("/api/site/{domain:path}")
async def get_site(domain: str):
    """Return full profile for a single domain."""
    domain = domain.lower().strip().lstrip("www.")
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id, domain, first_seen, last_crawled, status, last_status_code, crawl_tier"
            " FROM sites WHERE LOWER(REPLACE(domain,'www.','')) = ? LIMIT 1",
            (domain,),
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Site not found")
        site_id, site_domain, first_seen, last_crawled, status, status_code, tier = row

        cur2 = await db.execute(
            "SELECT t.name, t.category, t.website, st.confidence, st.version"
            " FROM site_technologies st"
            " JOIN technologies t ON st.tech_id = t.id"
            " WHERE st.site_id = ? ORDER BY st.confidence DESC, t.category",
            (site_id,),
        )
        techs = [
            {"name": r[0], "category": r[1], "website": r[2],
             "confidence": r[3], "version": r[4] or ""}
            for r in await cur2.fetchall()
        ]

    categories: dict[str, list] = {}
    for t in techs:
        cat = t["category"]
        categories.setdefault(cat, []).append(t)

    return {
        "domain": site_domain,
        "status": status,
        "status_code": status_code,
        "first_seen": first_seen,
        "last_crawled": last_crawled,
        "crawl_tier": tier,
        "tech_count": len(techs),
        "technologies": techs,
        "by_category": categories,
    }


# ── Crawl management endpoints ────────────────────────────────────────────────

class CrawlReq(BaseModel):
    domain: str


class CrawlBatchReq(BaseModel):
    domains: list[str]


@app.post("/api/crawl")
async def crawl_domain(req: CrawlReq):
    """Immediately crawl a single domain and return detections."""
    from pipeline import crawl_and_store
    from db.store import init_db
    await init_db()
    domain = req.domain.lower().strip().lstrip("www.")
    result = await crawl_and_store(domain, verbose=False)
    return {
        "domain": result.domain,
        "status_code": result.status_code,
        "detections": len(result.detections),
        "crawl_time": round(result.crawl_time, 2),
        "error": result.error,
        "technologies": result.detections,
    }


@app.post("/api/crawl/batch")
async def crawl_batch_api(req: CrawlBatchReq):
    """Add multiple domains to the crawl queue (crawled in background)."""
    from db.store import init_db
    await init_db()
    domains = [d.lower().strip().lstrip("www.") for d in req.domains if d.strip()]
    async with aiosqlite.connect(DB_PATH) as db:
        for domain in domains:
            await db.execute(
                "INSERT INTO sites (domain) VALUES (?) ON CONFLICT(domain) DO NOTHING",
                (domain,),
            )
        await db.commit()
    return {"queued": len(domains), "domains": domains}


@app.get("/api/export.csv")
async def export_csv(
    must_have: str = "",
    must_not_have: str = "",
    any_of: str = "",
    category: str = "",
    limit: int = 2000,
):
    mh = [t for t in must_have.split(",") if t.strip()]
    mnh = [t for t in must_not_have.split(",") if t.strip()]
    ao = [t for t in any_of.split(",") if t.strip()]
    sites = await _run_query(mh, mnh, ao, category, limit)

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["domain", "tech_count", "technologies"])
    for s in sites:
        w.writerow([s["domain"], s["tech_count"],
                    ", ".join(t["name"] for t in s["technologies"])])
    buf.seek(0)

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=techspy_leads.csv"},
    )


# ── Site profile SPA route ────────────────────────────────────────────────────

@app.get("/site/{domain:path}")
async def site_page(domain: str):
    """Serve the site detail SPA for any /site/<domain> path."""
    return FileResponse(str(WEBSITE_DIR / "site.html"))


# ── Static files (must be last) ───────────────────────────────────────────────
app.mount("/", StaticFiles(directory=str(WEBSITE_DIR), html=True), name="static")
