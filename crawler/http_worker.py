"""
Async HTTP fetcher using curl_cffi for TLS fingerprint impersonation.
Falls back to aiohttp for domains where curl_cffi fails.
"""
import asyncio
import aiohttp
from dataclasses import dataclass
from config import CRAWL_TIMEOUT, MAX_CONCURRENT_CRAWLS

try:
    from curl_cffi.requests import AsyncSession as CurlSession
    HAS_CURL = True
except ImportError:
    HAS_CURL = False


@dataclass
class FetchResult:
    url: str
    status_code: int
    headers: dict
    body: bytes
    error: str = ""


_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(MAX_CONCURRENT_CRAWLS)
    return _semaphore


def _ensure_https(domain: str) -> str:
    if domain.startswith("http://") or domain.startswith("https://"):
        return domain
    return f"https://{domain}"


async def fetch(domain: str) -> FetchResult:
    url = _ensure_https(domain)
    async with _get_semaphore():
        if HAS_CURL:
            result = await _fetch_curl(url)
            if not result.error:
                return result
        return await _fetch_aiohttp(url)


async def _fetch_curl(url: str) -> FetchResult:
    """Use curl_cffi to impersonate Chrome TLS fingerprint."""
    try:
        async with CurlSession(impersonate="chrome120") as session:
            resp = await session.get(
                url,
                timeout=CRAWL_TIMEOUT,
                follow_redirects=True,
                max_redirects=5,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                    "Accept-Encoding": "gzip, deflate, br",
                    "DNT": "1",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                },
            )
            body = resp.content
            headers = dict(resp.headers)
            return FetchResult(url=str(resp.url), status_code=resp.status_code, headers=headers, body=body)
    except Exception as e:
        return FetchResult(url=url, status_code=0, headers={}, body=b"", error=str(e))


async def _fetch_aiohttp(url: str) -> FetchResult:
    """Fallback: standard aiohttp."""
    connector = aiohttp.TCPConnector(ssl=False, limit=MAX_CONCURRENT_CRAWLS)
    timeout = aiohttp.ClientTimeout(total=CRAWL_TIMEOUT)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    try:
        async with aiohttp.ClientSession(connector=connector, timeout=timeout, headers=headers) as session:
            async with session.get(url, allow_redirects=True, max_redirects=5) as resp:
                body = await resp.read()
                return FetchResult(
                    url=str(resp.url),
                    status_code=resp.status,
                    headers=dict(resp.headers),
                    body=body,
                )
    except Exception as e:
        return FetchResult(url=url, status_code=0, headers={}, body=b"", error=str(e))


async def fetch_many(domains: list[str]) -> list[FetchResult]:
    """Fetch multiple domains concurrently."""
    tasks = [fetch(d) for d in domains]
    return await asyncio.gather(*tasks, return_exceptions=False)
