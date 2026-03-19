"""
Convert wappalyzer-zeeshan npm package technologies to our technologies.json format
and merge with existing fingerprints.
"""
import urllib.request
import tarfile
import io
import json
import re
from pathlib import Path

TECH_FILE = Path("C:/Users/yndxs/techspy/detection/technologies.json")
OUT_FILE = Path("C:/Users/yndxs/techspy/detection/technologies.json")

def clean_pattern(p) -> str:
    """Strip wappalyzer-specific \\;version:\\1 groups from patterns."""
    if not p:
        return ""
    s = str(p)
    # Remove \;key:value suffixes
    s = re.sub(r"\\;[a-z]+:[^\\]*", "", s)
    return s.strip("\\;")

def to_str_list(v) -> list:
    if isinstance(v, str):
        return [v] if v else []
    if isinstance(v, list):
        return [str(x) for x in v if x]
    return []

def clean_implies(lst: list) -> list:
    result = []
    for x in lst:
        x = str(x)
        # Remove \;confidence:75 etc.
        x = re.sub(r"\\;.*", "", x)
        x = x.strip()
        if x:
            result.append(x)
    return result


def main():
    print("Downloading wappalyzer-zeeshan...")
    url = "https://registry.npmjs.org/wappalyzer-zeeshan/-/wappalyzer-zeeshan-8.0.0.tgz"
    req = urllib.request.urlopen(url, timeout=60)
    data = req.read()
    print(f"Downloaded {len(data):,} bytes")

    tf = tarfile.open(fileobj=io.BytesIO(data), mode="r:gz")

    # Load categories
    cats_map = {}
    for member in tf.getmembers():
        if member.name == "package/categories.json":
            f = tf.extractfile(member)
            cats_raw = json.loads(f.read())
            cats_map = {str(k): v["name"] for k, v in cats_raw.items()}
    print(f"Categories: {len(cats_map)}")

    # Load all technologies
    wap_techs = {}
    for member in tf.getmembers():
        if "technologies/" in member.name and member.name.endswith(".json"):
            f = tf.extractfile(member)
            if f:
                wap_techs.update(json.loads(f.read()))
    print(f"Wappalyzer technologies: {len(wap_techs)}")

    # Convert to our format
    converted = {}
    for name, tech in wap_techs.items():
        cat_ids = tech.get("cats", [])
        categories = [cats_map.get(str(c), f"cat{c}") for c in cat_ids]
        if not categories:
            categories = ["Miscellaneous"]

        patterns = {}

        # Headers
        hdr = tech.get("headers", {})
        if hdr and isinstance(hdr, dict):
            patterns["headers"] = {k: clean_pattern(v) for k, v in hdr.items()}

        # HTML patterns
        html_list = to_str_list(tech.get("html", ""))
        if html_list:
            patterns["html"] = [clean_pattern(p) for p in html_list if p]

        # Script sources
        script_list = to_str_list(tech.get("scriptSrc", ""))
        if script_list:
            patterns["scripts"] = [clean_pattern(p) for p in script_list if p]

        # Cookies
        cookies = tech.get("cookies", {})
        if cookies and isinstance(cookies, dict):
            patterns["cookies"] = list(cookies.keys())

        # JS globals
        js = tech.get("js", {})
        if js and isinstance(js, dict):
            patterns["js_globals"] = list(js.keys())

        # Meta tags
        meta = tech.get("meta", {})
        if meta and isinstance(meta, dict):
            for k, v in meta.items():
                if k.lower() == "generator":
                    patterns["meta_generator"] = clean_pattern(v)
                else:
                    patterns.setdefault("meta_tags", {})[k] = clean_pattern(v)

        # Implies
        implies_raw = tech.get("implies", [])
        if isinstance(implies_raw, str):
            implies_raw = [implies_raw]
        implies_list = clean_implies(implies_raw)

        converted[name] = {
            "categories": categories,
            "website": tech.get("website", ""),
            "implies": implies_list,
            "patterns": patterns,
        }

    # Load our existing technologies.json
    existing = json.loads(TECH_FILE.read_text(encoding="utf-8"))
    print(f"Existing technologies: {len(existing)}")

    # Merge: only add techs we don't already have
    added = 0
    skipped = 0
    for name, tech in converted.items():
        if name not in existing:
            existing[name] = tech
            added += 1
        else:
            skipped += 1

    print(f"Added: {added}, Skipped (already exist): {skipped}")
    print(f"Total after merge: {len(existing)}")

    # Save
    OUT_FILE.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"Saved to {OUT_FILE}")

    # Print some key technology samples
    for name in ["WordPress", "React", "Cloudflare CDN", "Google Analytics", "Shopify", "Next.js"]:
        if name in existing:
            t = existing[name]
            print(f"  {name}: cats={t['categories']}, patterns={list(t['patterns'].keys())}")


if __name__ == "__main__":
    main()
