"""
Scrape technology names + categories from trends.builtwith.com.

Output: builtwith_techs.json
  {
    "category_tree": { "Advertising": ["Ad Server", "Ad Network", ...], ... },
    "technologies":  { "DoubleClick.Net": { "categories": ["Advertising", "Ad Server"], "sites": 555477 }, ... }
  }

Usage: py scrape_builtwith.py
"""
import asyncio
import json
import re
import time
from pathlib import Path

from curl_cffi.requests import AsyncSession as CurlSession
from bs4 import BeautifulSoup

SUBCATS_FILE = Path("C:/Users/yndxs/Downloads/bw_subcats.json")
OUTPUT_FILE  = Path("builtwith_techs.json")
PROGRESS_FILE = Path("builtwith_progress.json")

# Only scrape these top categories (skip ads.txt noise, domain parking, etc.)
ALLOWED_TOP_CATS = {
    "ads":        "Advertising",
    "analytics":  "Analytics",
    "av":         "Media",
    "cdns":       "CDN",
    "cdn":        "CDN",
    "framework":  "Frameworks",
    "javascript": "JavaScript Libraries",
    "mapping":    "Mapping",
    "mx":         "Email Hosting",
    "ns":         "DNS",
    "os":         "Hosting",
    "payment":    "Payment",
    "server":     "Web Servers",
    "web-server": "Web Servers",
    "web":        "Web Servers",
    "hosting":    "Web Hosting",
    "ssl":        "SSL",
    "widgets":    "Widgets",
    "shop":       "eCommerce",
    "cms":        "CMS",
    "media":      "Media",
    "wp":         "WordPress",
}

CONCURRENCY = 5       # parallel requests
DELAY       = 0.4     # seconds between batches
TIMEOUT     = 15      # request timeout

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://trends.builtwith.com/",
}


def parse_int(s: str) -> int:
    try:
        return int(re.sub(r"[^\d]", "", s))
    except Exception:
        return 0


async def fetch_page(session: CurlSession, url: str, retries: int = 2) -> str | None:
    for attempt in range(retries + 1):
        try:
            resp = await session.get(url, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
            if resp.status_code == 200:
                return resp.text
            elif resp.status_code == 429:
                wait = 10 * (attempt + 1)
                print(f"  [429] rate limited on {url}, waiting {wait}s")
                await asyncio.sleep(wait)
            else:
                return None
        except Exception as e:
            if attempt < retries:
                await asyncio.sleep(2)
            else:
                print(f"  [ERR] {url}: {e}")
                return None
    return None


def extract_techs(html: str, top_cat_name: str, sub_cat_name: str) -> list[dict]:
    """Parse technology rows from a subcategory page."""
    soup = BeautifulSoup(html, "lxml")
    results = []

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            a = row.find("a")
            if not a:
                continue
            name = a.get_text(strip=True)
            if not name or len(name) > 100:
                continue

            # Find the site count cell (usually 2nd or 3rd column with a number)
            sites = 0
            for cell in cells[1:]:
                txt = cell.get_text(strip=True).replace(",", "").replace(" ", "")
                if txt.isdigit():
                    sites = int(txt)
                    break

            if name and sites > 0:
                results.append({
                    "name": name,
                    "top_category": top_cat_name,
                    "sub_category": sub_cat_name,
                    "sites": sites,
                })

    return results


async def scrape_all():
    subcats = json.loads(SUBCATS_FILE.read_text(encoding="utf-8"))

    # Filter to allowed categories only
    subcats = [s for s in subcats if s["topCat"] in ALLOWED_TOP_CATS]
    print(f"Subcategories to scrape: {len(subcats)}")

    # Load progress
    progress: dict = {}
    if PROGRESS_FILE.exists():
        progress = json.loads(PROGRESS_FILE.read_text())
        print(f"Resuming from progress: {len(progress)} already done")

    # All collected techs: name → {categories, sites}
    all_techs: dict = {}
    category_tree: dict = {}  # top_cat → set of sub_cats

    # Load existing results if any
    if OUTPUT_FILE.exists():
        existing = json.loads(OUTPUT_FILE.read_text())
        all_techs = existing.get("technologies", {})
        for cat, subs in existing.get("category_tree", {}).items():
            category_tree[cat] = set(subs)

    sem = asyncio.Semaphore(CONCURRENCY)
    done = 0
    total = len(subcats)

    async def process(session, subcat):
        nonlocal done
        href = subcat["href"]
        top_cat = ALLOWED_TOP_CATS[subcat["topCat"]]
        sub_name = subcat["name"]

        if href in progress:
            done += 1
            return

        async with sem:
            html = await fetch_page(session, href)
            await asyncio.sleep(DELAY)

        if not html:
            progress[href] = "error"
            done += 1
            return

        techs = extract_techs(html, top_cat, sub_name)
        for t in techs:
            name = t["name"]
            if name not in all_techs:
                all_techs[name] = {
                    "categories": [t["top_category"], t["sub_category"]],
                    "sites": t["sites"],
                }
            else:
                # Update with highest site count
                if t["sites"] > all_techs[name]["sites"]:
                    all_techs[name]["sites"] = t["sites"]
                # Add categories if not present
                for c in [t["top_category"], t["sub_category"]]:
                    if c not in all_techs[name]["categories"]:
                        all_techs[name]["categories"].append(c)

        # Update category tree
        if top_cat not in category_tree:
            category_tree[top_cat] = set()
        category_tree[top_cat].add(sub_name)

        progress[href] = len(techs)
        done += 1

        if done % 20 == 0 or done == total:
            pct = done / total * 100
            print(f"  [{done}/{total}] {pct:.0f}% — {len(all_techs)} unique techs so far")
            _save(all_techs, category_tree)
            PROGRESS_FILE.write_text(json.dumps(progress, indent=2))

    async with CurlSession(impersonate="chrome120") as session:
        await asyncio.gather(*[process(session, s) for s in subcats])

    _save(all_techs, category_tree)
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2))
    print(f"\nDone! {len(all_techs)} unique technologies scraped.")
    print(f"Saved to {OUTPUT_FILE}")


def _save(all_techs, category_tree):
    OUTPUT_FILE.write_text(json.dumps({
        "category_tree": {k: sorted(v) for k, v in category_tree.items()},
        "technologies": dict(sorted(all_techs.items(), key=lambda x: -x[1]["sites"])),
    }, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    t0 = time.time()
    asyncio.run(scrape_all())
    print(f"Total time: {time.time()-t0:.0f}s")
