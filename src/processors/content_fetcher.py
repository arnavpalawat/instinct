"""Fetch full article content from URLs using trafilatura."""

import hashlib
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock
from urllib.parse import urlparse

import trafilatura

from src.models.article import Article

logger = logging.getLogger(__name__)

PAYWALLED_DOMAINS = {
    "wsj.com",
    "ft.com",
    "bloomberg.com",
    "barrons.com",
    "economist.com",
    "theathletic.com",
    "nytimes.com",
    "washingtonpost.com",
}

SKIP_DOMAINS = {
    "sec.gov",  # SEC EDGAR — already structured data
}

MAX_CONTENT_LENGTH = 5000
RATE_LIMIT_DELAY = 0.5  # seconds between requests to the same domain
DEFAULT_WORKERS = 5
CACHE_DIR = Path(".cache/content")


class ContentFetcher:
    """Fetches and extracts full article text from URLs.

    Features:
    - Parallel fetching via ThreadPoolExecutor
    - Per-domain rate limiting
    - Skips paywalled and SEC EDGAR domains
    - File-based cache keyed by URL hash
    - Graceful failure per article
    """

    def __init__(self, config: dict | None = None):
        config = config or {}
        content_config = config.get("content_fetcher", {})
        self.max_workers = content_config.get("max_workers", DEFAULT_WORKERS)
        self.max_length = content_config.get("max_length", MAX_CONTENT_LENGTH)
        self.rate_limit = content_config.get("rate_limit_delay", RATE_LIMIT_DELAY)
        self.cache_enabled = content_config.get("cache_enabled", True)

        extra_skip = set(content_config.get("skip_domains", []))
        self.skip_domains = PAYWALLED_DOMAINS | SKIP_DOMAINS | extra_skip

        self._domain_locks: dict[str, float] = {}
        self._lock = Lock()

        if self.cache_enabled:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def fetch_all(self, articles: list[Article]) -> list[Article]:
        """Fetch full content for all articles in parallel.

        Modifies articles in place, setting raw_content where successful.
        Returns the same list for chaining.
        """
        to_fetch = [a for a in articles if not a.raw_content and a.url and not self._should_skip(a.url)]
        if not to_fetch:
            logger.info("Content fetch: nothing to fetch (all cached/skipped)")
            return articles

        succeeded = 0
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {pool.submit(self._fetch_one, a): a for a in to_fetch}
            for future in as_completed(futures):
                article = futures[future]
                try:
                    content = future.result()
                    if content:
                        article.raw_content = content
                        succeeded += 1
                except Exception as exc:
                    logger.debug("Fetch failed for '%s': %s", article.title[:60], exc)

        logger.info("Content fetch complete: %d/%d succeeded", succeeded, len(to_fetch))
        return articles

    def _fetch_one(self, article: Article) -> str:
        """Fetch content for a single article. Returns extracted text or empty string."""
        # Check cache first
        cached = self._cache_get(article.url)
        if cached is not None:
            return cached

        # Rate limit per domain
        self._rate_limit(article.url)

        try:
            downloaded = trafilatura.fetch_url(article.url)
            if not downloaded:
                return ""

            text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
            if not text:
                return ""

            text = text[:self.max_length]
            self._cache_set(article.url, text)
            return text
        except Exception as exc:
            logger.debug("trafilatura error for %s: %s", article.url, exc)
            return ""

    def _should_skip(self, url: str) -> bool:
        """Check if URL belongs to a paywalled or skipped domain."""
        try:
            domain = urlparse(url).netloc.lower()
            return any(domain == d or domain.endswith("." + d) for d in self.skip_domains)
        except Exception:
            return False

    def _rate_limit(self, url: str) -> None:
        """Enforce per-domain rate limiting."""
        try:
            domain = urlparse(url).netloc.lower()
        except Exception:
            return

        with self._lock:
            last = self._domain_locks.get(domain, 0)
            now = time.monotonic()
            wait = self.rate_limit - (now - last)
            if wait > 0:
                time.sleep(wait)
            self._domain_locks[domain] = time.monotonic()

    def _url_hash(self, url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def _cache_get(self, url: str) -> str | None:
        if not self.cache_enabled:
            return None
        path = CACHE_DIR / f"{self._url_hash(url)}.json"
        if path.exists():
            try:
                data = json.loads(path.read_text())
                return data.get("content", "")
            except Exception:
                return None
        return None

    def _cache_set(self, url: str, content: str) -> None:
        if not self.cache_enabled:
            return
        path = CACHE_DIR / f"{self._url_hash(url)}.json"
        try:
            path.write_text(json.dumps({"url": url, "content": content}))
        except Exception:
            pass
