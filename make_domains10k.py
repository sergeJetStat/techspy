"""
Fetch top 10 000 domains from the Tranco list and merge with local domain files.
Output: domains10k.txt (deduplicated, one domain per line)
"""
import io
import zipfile
import urllib.request
from pathlib import Path

TRANCO_URL = "https://tranco-list.eu/top-1m.csv.zip"
TARGET = 10_000
OUT_FILE = Path(__file__).parent / "domains10k.txt"

# ── local lists already crawled / hand-curated ───────────────────────────────
LOCAL_FILES = [
    "domains1000.txt",
    "domains1000_clean.txt",
    "ru_domains.txt",
    "domains100.txt",
]

def load_local() -> set[str]:
    seen: set[str] = set()
    for fname in LOCAL_FILES:
        p = Path(__file__).parent / fname
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                d = line.strip().lower()
                if d and not d.startswith("#"):
                    # strip protocol if present
                    d = d.removeprefix("https://").removeprefix("http://").rstrip("/")
                    seen.add(d)
    print(f"Loaded {len(seen)} domains from local files")
    return seen


def fetch_tranco() -> list[str]:
    print(f"Downloading Tranco top-1M list …")
    req = urllib.request.Request(TRANCO_URL, headers={"User-Agent": "TechSpy/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    print(f"Downloaded {len(data)//1024} KB, extracting …")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        csv_name = z.namelist()[0]
        csv_text = z.read(csv_name).decode("utf-8")
    domains = []
    for line in csv_text.splitlines():
        parts = line.strip().split(",")
        if len(parts) >= 2:
            domains.append(parts[1].strip().lower())
    print(f"Tranco list: {len(domains)} entries")
    return domains


def main():
    local = load_local()

    try:
        tranco = fetch_tranco()
    except Exception as exc:
        print(f"Could not fetch Tranco list: {exc}")
        print("Using local files only")
        tranco = []

    # merge: local first (higher quality, already crawled or curated),
    # then fill from Tranco until we have TARGET unique domains
    result: list[str] = list(local)
    seen = set(local)
    for d in tranco:
        if len(result) >= TARGET:
            break
        if d not in seen:
            seen.add(d)
            result.append(d)

    # trim to TARGET
    result = result[:TARGET]

    OUT_FILE.write_text("\n".join(result) + "\n", encoding="utf-8")
    print(f"\nWrote {len(result)} domains -> {OUT_FILE.name}")


if __name__ == "__main__":
    main()
