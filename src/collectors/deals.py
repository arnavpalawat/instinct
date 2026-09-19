"""Deal announcement collector from PR Newswire and BusinessWire RSS feeds."""
import logging
import re
from datetime import datetime
from typing import Optional

import feedparser

from src.models.article import Article

logger = logging.getLogger(__name__)


class DealCollector:
    """Collects deal-related press releases from PR Newswire and BusinessWire."""

    PRNEWSWIRE_FEEDS = [
        "https://www.prnewswire.com/rss/financial-services-latest-news/financial-services-latest-news-list.jsp",
        "https://www.prnewswire.com/rss/mergers-and-acquisitions-latest-news/mergers-and-acquisitions-latest-news-list.jsp",
    ]

    BUSINESSWIRE_FEED = (
        "https://feed.businesswire.com/rss/home/?rss=G1QFDERJXkJeGVtRVg=="
    )

    DEAL_KEYWORDS = [
        "acquire",
        "acquisition",
        "merger",
        "merge",
        "buyout",
        "take-private",
        "definitive agreement",
        "strategic combination",
        "transaction",
        "purchase agreement",
        "tender offer",
        "divestiture",
        "spin-off",
        "spinoff",
        "joint venture",
        "recapitalization",
    ]

    # Pre-compile a single pattern for efficiency
    _DEAL_PATTERN = re.compile(
        "|".join(re.escape(kw) for kw in DEAL_KEYWORDS),
        re.IGNORECASE,
    )

    def __init__(self, config: dict):
        self.config = config

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def collect(self) -> list[Article]:
        """Collect deal-related articles from all RSS sources."""
        articles: list[Article] = []
        seen_ids: set[str] = set()

        def _add(batch: list[Article]) -> None:
            for a in batch:
                if a.id not in seen_ids:
                    seen_ids.add(a.id)
                    articles.append(a)

        _add(self._fetch_prnewswire())
        _add(self._fetch_businesswire())

        logger.info("Deal collection complete: %d articles", len(articles))
        return articles

    # ------------------------------------------------------------------
    # PR Newswire
    # ------------------------------------------------------------------

    def _fetch_prnewswire(self) -> list[Article]:
        """Fetch deal-related press releases from PR Newswire RSS feeds.

        The M&A feed is inherently deal-related so all entries are kept.
        The financial services feed is filtered for deal keywords.
        """
        articles: list[Article] = []

        for feed_url in self.PRNEWSWIRE_FEEDS:
            is_ma_feed = "mergers-and-acquisitions" in feed_url
            try:
                feed = feedparser.parse(feed_url)

                if feed.bozo and not feed.entries:
                    logger.debug(
                        "PR Newswire RSS error for %s: %s",
                        feed_url, feed.bozo_exception,
                    )
                    continue

                for entry in feed.entries:
                    try:
                        title = entry.get("title", "")
                        summary = entry.get("summary", "") or entry.get("description", "")

                        # M&A feed: keep everything. Other feeds: filter.
                        if not is_ma_feed and not self._is_deal_related(title, summary):
                            continue

                        published = self._parse_feed_date(entry)

                        articles.append(Article(
                            title=title,
                            url=entry.get("link", ""),
                            source="pr_newswire",
                            published=published,
                            summary=summary[:500],
                            is_deal_related=True,
                        ))
                    except Exception as exc:
                        logger.debug("Failed to parse PR Newswire entry: %s", exc)
            except Exception as exc:
                logger.warning("PR Newswire RSS fetch failed for %s: %s", feed_url, exc)

        return articles

    # ------------------------------------------------------------------
    # BusinessWire
    # ------------------------------------------------------------------

    def _fetch_businesswire(self) -> list[Article]:
        """Fetch deal-related press releases from BusinessWire RSS feed.

        All entries are filtered through the deal-keyword detector.
        """
        articles: list[Article] = []

        try:
            feed = feedparser.parse(self.BUSINESSWIRE_FEED)

            if feed.bozo and not feed.entries:
                logger.debug(
                    "BusinessWire RSS error: %s", feed.bozo_exception,
                )
                return articles

            for entry in feed.entries:
                try:
                    title = entry.get("title", "")
                    summary = entry.get("summary", "") or entry.get("description", "")

                    if not self._is_deal_related(title, summary):
                        continue

                    published = self._parse_feed_date(entry)

                    articles.append(Article(
                        title=title,
                        url=entry.get("link", ""),
                        source="businesswire",
                        published=published,
                        summary=summary[:500],
                        is_deal_related=True,
                    ))
                except Exception as exc:
                    logger.debug("Failed to parse BusinessWire entry: %s", exc)
        except Exception as exc:
            logger.warning("BusinessWire RSS fetch failed: %s", exc)

        return articles

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_deal_related(self, title: str, summary: str) -> bool:
        """Return True if either the title or summary contains deal-related keywords."""
        text = f"{title} {summary}"
        return bool(self._DEAL_PATTERN.search(text))

    @staticmethod
    def _parse_feed_date(entry) -> Optional[datetime]:
        """Extract and parse a datetime from an RSS feed entry."""
        try:
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                return datetime(*entry.published_parsed[:6])
            if hasattr(entry, "updated_parsed") and entry.updated_parsed:
                return datetime(*entry.updated_parsed[:6])
        except Exception:
            pass
        return None
