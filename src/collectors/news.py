"""News collector using Finnhub and Google News RSS."""
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote_plus

import feedparser
import finnhub

from src.models.article import Article

logger = logging.getLogger(__name__)

# Finnhub free tier: 60 API calls/minute
_FINNHUB_CALL_INTERVAL = 1.1  # seconds between calls to stay under limit


class NewsCollector:
    """Collects financial news from Finnhub and Google News RSS feeds."""

    DEFAULT_RSS_QUERIES = [
        "M&A deal acquisition",
        "private equity buyout",
        "leveraged finance",
        "capital markets IPO",
        "debt financing bond issuance",
    ]

    SECTOR_RSS_QUERIES = {
        "technology": "technology acquisition deal",
        "healthcare": "healthcare pharma acquisition",
        "financial_services": "financial services deal merger",
        "energy": "energy pipeline acquisition deal",
        "industrials": "industrial merger acquisition",
        "consumer": "consumer retail acquisition deal",
        "real_estate": "real estate REIT acquisition",
        "telecom": "telecom media acquisition deal",
    }

    GOOGLE_NEWS_RSS_BASE = (
        "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    )

    def __init__(self, config: dict):
        self.config = config
        self.finnhub_key = os.environ.get("FINNHUB_API_KEY", "")

        self.finnhub_client: Optional[finnhub.Client] = None
        if self.finnhub_key:
            try:
                self.finnhub_client = finnhub.Client(api_key=self.finnhub_key)
            except Exception as exc:
                logger.warning("Failed to initialise Finnhub client: %s", exc)

        self._last_finnhub_call: float = 0.0

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def collect(self, sectors: Optional[list[str]] = None) -> list[Article]:
        """Collect news from all sources and return a combined list.

        Args:
            sectors: Optional list of sector names to include sector-specific
                     Google News queries (e.g. ["technology", "healthcare"]).
        """
        articles: list[Article] = []
        seen_ids: set[str] = set()

        def _add(batch: list[Article]) -> None:
            for a in batch:
                if a.id not in seen_ids:
                    seen_ids.add(a.id)
                    articles.append(a)

        # 1. Finnhub general news
        _add(self._fetch_finnhub_news(category="general"))

        # 2. Google News RSS (default queries)
        queries = list(self.DEFAULT_RSS_QUERIES)
        if sectors:
            for s in sectors:
                q = self.SECTOR_RSS_QUERIES.get(s.lower())
                if q:
                    queries.append(q)
        _add(self._fetch_google_news_rss(queries))

        # 3. Company-specific news for watchlist tickers
        watchlist = self.config.get("watchlist", [])
        if watchlist:
            _add(self._fetch_company_news(watchlist))

        logger.info("News collection complete: %d articles", len(articles))
        return articles

    # ------------------------------------------------------------------
    # Finnhub general news
    # ------------------------------------------------------------------

    def _fetch_finnhub_news(self, category: str = "general") -> list[Article]:
        """Fetch general market news from Finnhub."""
        if not self.finnhub_client:
            logger.warning("Finnhub client not available; skipping general news")
            return []

        articles: list[Article] = []
        try:
            self._rate_limit_finnhub()
            raw_news = self.finnhub_client.general_news(category, min_id=0)
            if not raw_news:
                return articles

            for item in raw_news:
                try:
                    published = None
                    ts = item.get("datetime")
                    if ts:
                        published = datetime.fromtimestamp(int(ts))

                    articles.append(Article(
                        title=item.get("headline", ""),
                        url=item.get("url", ""),
                        source="finnhub",
                        published=published,
                        summary=item.get("summary", ""),
                        tickers=([item["related"]] if item.get("related") else []),
                    ))
                except Exception as exc:
                    logger.debug("Failed to parse Finnhub news item: %s", exc)
        except Exception as exc:
            logger.error("Finnhub general_news call failed: %s", exc)

        return articles

    # ------------------------------------------------------------------
    # Google News RSS
    # ------------------------------------------------------------------

    def _fetch_google_news_rss(self, queries: list[str]) -> list[Article]:
        """Parse Google News RSS feeds for the given search queries."""
        articles: list[Article] = []

        for query in queries:
            try:
                url = self.GOOGLE_NEWS_RSS_BASE.format(query=quote_plus(query))
                feed = feedparser.parse(url)

                if feed.bozo and not feed.entries:
                    logger.debug("RSS feed error for query '%s': %s", query, feed.bozo_exception)
                    continue

                for entry in feed.entries:
                    try:
                        published = None
                        if hasattr(entry, "published_parsed") and entry.published_parsed:
                            published = datetime(*entry.published_parsed[:6])

                        summary = getattr(entry, "summary", "") or ""
                        # Google News summaries contain HTML; strip basic tags
                        summary = summary.replace("<b>", "").replace("</b>", "")
                        summary = summary.replace("<a ", "").replace("</a>", "")

                        articles.append(Article(
                            title=entry.get("title", ""),
                            url=entry.get("link", ""),
                            source="google_news",
                            published=published,
                            summary=summary[:500],
                        ))
                    except Exception as exc:
                        logger.debug("Failed to parse RSS entry: %s", exc)
            except Exception as exc:
                logger.warning("Google News RSS fetch failed for '%s': %s", query, exc)

        return articles

    # ------------------------------------------------------------------
    # Company-specific news (Finnhub)
    # ------------------------------------------------------------------

    def _fetch_company_news(self, tickers: list[str]) -> list[Article]:
        """Fetch company-specific news for watchlist tickers via Finnhub."""
        if not self.finnhub_client:
            logger.warning("Finnhub client not available; skipping company news")
            return []

        articles: list[Article] = []
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        for ticker in tickers:
            try:
                self._rate_limit_finnhub()
                raw_news = self.finnhub_client.company_news(
                    ticker, _from=yesterday, to=today
                )
                if not raw_news:
                    continue

                for item in raw_news:
                    try:
                        published = None
                        ts = item.get("datetime")
                        if ts:
                            published = datetime.fromtimestamp(int(ts))

                        articles.append(Article(
                            title=item.get("headline", ""),
                            url=item.get("url", ""),
                            source="finnhub",
                            published=published,
                            summary=item.get("summary", ""),
                            tickers=[ticker],
                        ))
                    except Exception as exc:
                        logger.debug("Failed to parse company news item for %s: %s", ticker, exc)
            except Exception as exc:
                logger.warning("Finnhub company_news failed for %s: %s", ticker, exc)

        return articles

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _rate_limit_finnhub(self) -> None:
        """Enforce a minimum interval between Finnhub API calls."""
        elapsed = time.time() - self._last_finnhub_call
        if elapsed < _FINNHUB_CALL_INTERVAL:
            time.sleep(_FINNHUB_CALL_INTERVAL - elapsed)
        self._last_finnhub_call = time.time()
