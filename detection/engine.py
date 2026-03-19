"""
Deterministic fingerprint matching engine.
Loads technologies.json and matches signals against patterns.
Returns detections with confidence scores.
"""
import re
import json
from pathlib import Path
from dataclasses import dataclass, field

TECH_DB_PATH = Path(__file__).parent / "technologies.json"

# Confidence weights
WEIGHT = {
    "headers": 90,
    "meta_generator": 85,
    "cookies": 70,
    "html": 65,
    "scripts": 60,
    "links": 55,
}

THRESHOLD = 60  # minimum confidence to report


@dataclass
class Detection:
    tech: str
    category: str
    website: str
    confidence: int
    version: str = ""
    signals_matched: list[str] = field(default_factory=list)


def _load_db() -> dict:
    with open(TECH_DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


_TECH_DB: dict | None = None


def get_tech_db() -> dict:
    global _TECH_DB
    if _TECH_DB is None:
        _TECH_DB = _load_db()
    return _TECH_DB


def detect(signals: dict) -> list[Detection]:
    """
    Run fingerprint matching on extracted signals.
    Returns list of detections above confidence threshold.
    """
    db = get_tech_db()
    detections: list[Detection] = []

    for tech_name, tech_data in db.items():
        patterns = tech_data.get("patterns", {})
        categories = tech_data.get("categories", ["Unknown"])
        website = tech_data.get("website", "")

        score = 0
        matched: list[str] = []
        version = ""

        # ── Headers ───────────────────────────────────────────────────────
        for header_name, pattern in patterns.get("headers", {}).items():
            value = signals["headers"].get(header_name.lower(), "")
            if value:
                if not pattern or _match(value, pattern):
                    score += WEIGHT["headers"]
                    matched.append(f"header:{header_name}")
                    v = _extract_version(value, pattern)
                    if v:
                        version = v

        # ── Meta Generator ────────────────────────────────────────────────
        gen_pattern = patterns.get("meta_generator", "")
        if gen_pattern and signals.get("meta_generator"):
            if _match(signals["meta_generator"], gen_pattern):
                score += WEIGHT["meta_generator"]
                matched.append("meta_generator")
                v = _extract_version(signals["meta_generator"], gen_pattern)
                if v:
                    version = v

        # ── Cookies ───────────────────────────────────────────────────────
        for cookie_prefix in patterns.get("cookies", []):
            for cookie in signals.get("cookies", []):
                if cookie.startswith(cookie_prefix) or cookie_prefix in cookie:
                    score += WEIGHT["cookies"]
                    matched.append(f"cookie:{cookie}")
                    break

        # ── Meta tags ─────────────────────────────────────────────────────
        for meta_name, meta_pattern in patterns.get("meta_tags", {}).items():
            meta_val = signals.get("meta_tags", {}).get(meta_name.lower(), "")
            if meta_val:
                if not meta_pattern or meta_pattern == ".*" or _match(meta_val, meta_pattern):
                    score += WEIGHT["meta_generator"]
                    matched.append(f"meta:{meta_name}")
                    v = _extract_version(meta_val, meta_pattern)
                    if v:
                        version = v

        # ── HTML patterns ─────────────────────────────────────────────────
        html_raw = signals.get("html_raw", "")
        for html_pattern in patterns.get("html", []):
            if html_pattern in html_raw:
                score += WEIGHT["html"]
                matched.append(f"html:{html_pattern[:40]}")

        # ── Script srcs ───────────────────────────────────────────────────
        for script_pattern in patterns.get("scripts", []):
            for src in signals.get("script_srcs", []):
                if script_pattern in src:
                    score += WEIGHT["scripts"]
                    matched.append(f"script:{src[:60]}")
                    break

        # ── Link hrefs ────────────────────────────────────────────────────
        for link_pattern in patterns.get("links", []):
            for href in signals.get("link_hrefs", []):
                if link_pattern in href:
                    score += WEIGHT["links"]
                    matched.append(f"link:{href[:60]}")
                    break

        # Cap score at 100
        final_score = min(score, 100)

        if final_score >= THRESHOLD and matched:
            detections.append(Detection(
                tech=tech_name,
                category=categories[0] if categories else "Unknown",
                website=website,
                confidence=final_score,
                version=version,
                signals_matched=matched,
            ))

    # Sort by confidence descending
    detections.sort(key=lambda d: d.confidence, reverse=True)
    return detections


def _match(value: str, pattern: str) -> bool:
    """Check if value contains pattern (case-insensitive substring or regex)."""
    if not pattern:
        return bool(value)
    try:
        return bool(re.search(pattern, value, re.IGNORECASE))
    except re.error:
        return pattern.lower() in value.lower()


def _extract_version(value: str, pattern: str) -> str:
    """Try to extract a version string from a matched header/meta value."""
    # Common version patterns: "WordPress 6.4.2", "PHP/8.2.0", "nginx/1.18.0"
    ver_match = re.search(r'[\s/v](\d+\.\d+(?:\.\d+)?)', value)
    if ver_match:
        return ver_match.group(1)
    return ""


def detections_to_dict(detections: list[Detection]) -> list[dict]:
    return [
        {
            "tech": d.tech,
            "category": d.category,
            "website": d.website,
            "confidence": d.confidence,
            "version": d.version,
            "signals_matched": d.signals_matched,
        }
        for d in detections
    ]


def find_unknown_signals(signals: dict, detections: list[Detection]) -> list[dict]:
    """
    Identify signals that didn't match any known technology.
    Returns candidate signals for the Detection Agent to investigate.
    """
    known_scripts: set[str] = set()
    known_headers: set[str] = set()
    db = get_tech_db()

    for tech_data in db.values():
        patterns = tech_data.get("patterns", {})
        for p in patterns.get("scripts", []):
            known_scripts.add(p)
        for h in patterns.get("headers", {}):
            known_headers.add(h.lower())

    unknown: list[dict] = []

    # Unknown script srcs (not matching any known pattern)
    for src in signals.get("script_srcs", []):
        if not any(k in src for k in known_scripts):
            # Filter out common CDNs and noise
            if any(cdn in src for cdn in ["googleapis", "gstatic", "w3.org", "schema.org"]):
                continue
            unknown.append({"signal_type": "script_src", "signal_value": src})

    # Interesting unknown headers
    interesting_headers = {"x-powered-by", "server", "x-generator", "x-platform"}
    for header_name, value in signals.get("headers", {}).items():
        if header_name.lower() in interesting_headers:
            if header_name.lower() not in known_headers or value:
                # Check if already matched
                already_matched = any(
                    f"header:{header_name}" in " ".join(d.signals_matched)
                    for d in detections
                )
                if not already_matched:
                    unknown.append({"signal_type": "header", "signal_value": f"{header_name}: {value}"})

    return unknown
