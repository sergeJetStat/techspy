"""
DNS-based technology detection.
Resolves MX and NS records for a domain to identify:
  - Email hosting providers (Google Workspace, Mail.ru, Yandex, Microsoft 365, etc.)
  - CDN / DNS providers (Cloudflare, NS1, etc.)
"""
import asyncio
import re
from dataclasses import dataclass, field

import dns.asyncresolver
import dns.exception

# ── MX fingerprints ──────────────────────────────────────────────────────────
# Pattern → (tech_name, category)
MX_PATTERNS: list[tuple[str, str, str]] = [
    # Google Workspace
    (r"aspmx\.l\.google\.com",          "Google Workspace",    "Email Hosting"),
    (r"googlemail\.com",                 "Google Workspace",    "Email Hosting"),
    (r"\.google\.com$",                  "Google Workspace",    "Email Hosting"),

    # Microsoft 365 / Outlook
    (r"\.mail\.protection\.outlook\.com","Microsoft 365 Mail",  "Email Hosting"),
    (r"\.olc\.protection\.outlook\.com", "Microsoft 365 Mail",  "Email Hosting"),

    # Yandex Mail
    (r"mx\.yandex\.(?:ru|net|com)",     "Yandex Mail",         "Email Hosting"),
    (r"mxs\.mail\.ru",                  "Mail.ru",             "Email Hosting"),

    # Mail.ru
    (r"\.mail\.ru$",                    "Mail.ru",             "Email Hosting"),

    # Amazon SES
    (r"amazonses\.com",                 "Amazon SES",          "Email Hosting"),

    # Proton Mail
    (r"protonmail\.ch",                 "Proton Mail",         "Email Hosting"),

    # Zoho Mail
    (r"zoho\.com",                      "Zoho Mail",           "Email Hosting"),

    # FastMail
    (r"fastmail\.com",                  "FastMail",            "Email Hosting"),

    # Mailgun
    (r"mailgun\.org",                   "Mailgun",             "Email Hosting"),

    # SendGrid
    (r"sendgrid\.net",                  "SendGrid MX",         "Email Hosting"),

    # Postmark
    (r"mtasv\.net",                     "Postmark",            "Email Hosting"),

    # iCloud
    (r"icloud\.com",                    "Apple iCloud Mail",   "Email Hosting"),

    # Namecheap / cPanel
    (r"privateemail\.com",              "Namecheap Email",     "Email Hosting"),

    # Reg.ru
    (r"mx\.(?:reg\.ru|reghost\.ru)",    "REG.RU Mail",         "Email Hosting"),

    # Timeweb
    (r"timeweb\.ru",                    "TimeWeb Mail",        "Email Hosting"),

    # RuVDS
    (r"ruvds\.com",                     "RuVDS",               "Email Hosting"),
]

# ── NS fingerprints ──────────────────────────────────────────────────────────
NS_PATTERNS: list[tuple[str, str, str]] = [
    # Cloudflare DNS
    (r"\.ns\.cloudflare\.com$",         "Cloudflare DNS",      "DNS"),

    # AWS Route 53
    (r"awsdns-",                        "AWS Route 53",        "DNS"),

    # Google Cloud DNS
    (r"googledomains\.com",             "Google Cloud DNS",    "DNS"),
    (r"dns\.google$",                   "Google Cloud DNS",    "DNS"),

    # Yandex Cloud DNS
    (r"yandexcloud\.net",               "Yandex Cloud DNS",    "DNS"),

    # NS1
    (r"\.nsone\.net$",                  "NS1 DNS",             "DNS"),

    # DNSimple
    (r"dnsimple\.com",                  "DNSimple",            "DNS"),

    # Namecheap DNS
    (r"registrar-servers\.com",         "Namecheap DNS",       "DNS"),

    # GoDaddy DNS
    (r"domaincontrol\.com",             "GoDaddy DNS",         "DNS"),

    # Reg.ru DNS
    (r"(?:rname|ns)\.reg\.ru$",         "REG.RU DNS",          "DNS"),

    # Beget
    (r"beget\.com",                     "Beget",               "Hosting"),

    # Selectel
    (r"selectel\.(?:ru|com)",           "Selectel DNS",        "DNS"),

    # TimeWeb
    (r"timeweb\.(?:ru|com|cloud)",      "TimeWeb",             "Hosting"),

    # RuCenter / RU-CENTER
    (r"nic\.ru$",                       "RU-CENTER DNS",       "DNS"),

    # Hetzner
    (r"hetzner\.com",                   "Hetzner",             "Hosting"),

    # DigitalOcean
    (r"digitalocean\.com",              "DigitalOcean DNS",    "DNS"),

    # Netlify
    (r"netlify\.com",                   "Netlify DNS",         "DNS"),

    # Vercel
    (r"vercel-dns\.com",                "Vercel DNS",          "DNS"),
]


@dataclass
class DnsDetection:
    tech: str
    category: str
    confidence: int = 80
    record_type: str = ""   # "MX" or "NS"
    matched_value: str = ""
    signals_matched: list[str] = field(default_factory=list)


async def detect_dns(domain: str, timeout: float = 5.0) -> list[DnsDetection]:
    """
    Resolve MX and NS records for domain and return detected technologies.
    """
    # Strip www.
    domain = re.sub(r"^www\.", "", domain.lower().strip())

    results: list[DnsDetection] = []
    resolver = dns.asyncresolver.Resolver()
    resolver.lifetime = timeout
    resolver.timeout = timeout

    # ── MX records ─────────────────────────────────────────────────────────
    try:
        mx_records = await resolver.resolve(domain, "MX")
        for rdata in mx_records:
            mx_host = str(rdata.exchange).rstrip(".").lower()
            for pattern, tech_name, category in MX_PATTERNS:
                if re.search(pattern, mx_host, re.IGNORECASE):
                    # Avoid duplicates
                    if not any(d.tech == tech_name for d in results):
                        results.append(DnsDetection(
                            tech=tech_name,
                            category=category,
                            confidence=85,
                            record_type="MX",
                            matched_value=mx_host,
                            signals_matched=[f"mx:{mx_host}"],
                        ))
    except (dns.exception.DNSException, Exception):
        pass

    # ── NS records ─────────────────────────────────────────────────────────
    try:
        ns_records = await resolver.resolve(domain, "NS")
        for rdata in ns_records:
            ns_host = str(rdata).rstrip(".").lower()
            for pattern, tech_name, category in NS_PATTERNS:
                if re.search(pattern, ns_host, re.IGNORECASE):
                    if not any(d.tech == tech_name for d in results):
                        results.append(DnsDetection(
                            tech=tech_name,
                            category=category,
                            confidence=80,
                            record_type="NS",
                            matched_value=ns_host,
                            signals_matched=[f"ns:{ns_host}"],
                        ))
    except (dns.exception.DNSException, Exception):
        pass

    return results


def dns_detections_to_dict(detections: list[DnsDetection]) -> list[dict]:
    return [
        {
            "tech": d.tech,
            "category": d.category,
            "website": "",
            "confidence": d.confidence,
            "version": "",
            "signals_matched": d.signals_matched,
        }
        for d in detections
    ]
