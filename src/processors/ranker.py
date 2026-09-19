"""Ranker: scores and sorts articles by relevance to IB/PE/PC recruiting."""

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from src.models.article import Article

logger = logging.getLogger(__name__)

# Deal-related keywords (case-insensitive matching).
DEAL_KEYWORDS: list[str] = [
    "acquire",
    "acquisition",
    "merger",
    "merge",
    "buyout",
    "take-private",
    "take private",
    "takeover",
    "leveraged buyout",
    "LBO",
    "carve-out",
    "carve out",
    "divestiture",
    "divest",
    "spin-off",
    "spin off",
    "IPO",
    "initial public offering",
    "definitive agreement",
    "letter of intent",
    "strategic alternatives",
    "going private",
    "tender offer",
    "bid",
    "consortium",
    "recapitalization",
    "joint venture",
    "stake",
    "controlling interest",
    "minority investment",
]

# Pre-compiled pattern for deal keyword matching.
_DEAL_PATTERN: re.Pattern = re.compile(
    r"\b(?:" + "|".join(re.escape(k) for k in DEAL_KEYWORDS) + r")\b",
    re.IGNORECASE,
)


class Ranker:
    """Score and sort articles by weighted relevance to finance recruiting.

    Weight schema
    -------------
    - Sector match (TMT/FIG primary sectors): +3.0
    - Deal-related article: +4.0
    - Watchlist ticker mention: +2.0 per ticker
    - Watchlist firm mention: +2.5 per firm
    - PE/PC sponsor mention: +3.0 (per unique sponsor)
    - Recency: last 6 h +2.0 | 6-12 h +1.0 | 12-24 h +0.5
    - Source authority: SEC filing +2.0 | PR wire +1.0 | news +0.5
    """

    def __init__(self, config_path: str = "config"):
        self._config_dir = Path(config_path)
        self._sectors: dict[str, Any] = {}
        self._watchlist_tickers: list[dict[str, Any]] = []
        self._watchlist_firms: list[dict[str, Any]] = []
        self._primary_sectors: list[str] = []
        self._sponsor_names: list[str] = []

        self._load_configs()

    # ------------------------------------------------------------------
    # Config loading
    # ------------------------------------------------------------------

    def _load_configs(self) -> None:
        """Load sectors.yaml and watchlist.yaml from the config directory."""
        sectors_path = self._config_dir / "sectors.yaml"
        watchlist_path = self._config_dir / "watchlist.yaml"
        settings_path = self._config_dir / "settings.yaml"

        if sectors_path.exists():
            with open(sectors_path, "r") as fh:
                self._sectors = yaml.safe_load(fh) or {}
            logger.info("Loaded %d sector definitions", len(self._sectors))
        else:
            logger.warning("sectors.yaml not found at %s", sectors_path)

        if watchlist_path.exists():
            with open(watchlist_path, "r") as fh:
                wl = yaml.safe_load(fh) or {}
            self._watchlist_tickers = wl.get("tickers", [])
            self._watchlist_firms = wl.get("firms", [])
            self._sponsor_names = [
                f["name"]
                for f in self._watchlist_firms
                if f.get("type") == "sponsor"
            ]
            logger.info(
                "Loaded watchlist: %d tickers, %d firms (%d sponsors)",
                len(self._watchlist_tickers),
                len(self._watchlist_firms),
                len(self._sponsor_names),
            )
        else:
            logger.warning("watchlist.yaml not found at %s", watchlist_path)

        if settings_path.exists():
            with open(settings_path, "r") as fh:
                settings = yaml.safe_load(fh) or {}
            self._primary_sectors = (
                settings.get("sectors", {}).get("primary", [])
            )
        else:
            self._primary_sectors = ["TMT", "FIG"]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def rank(self, articles: list[Article]) -> list[Article]:
        """Score every article and return sorted by relevance (descending)."""
        for article in articles:
            article.relevance_score = self._score(article)
        return sorted(articles, key=lambda a: a.relevance_score, reverse=True)

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _score(self, article: Article) -> float:
        """Compute weighted relevance score for a single article."""
        score = 0.0
        text = self._searchable_text(article)

        # 1. Sector match for primary sectors
        score += self._score_sector_match(text, article)

        # 2. Deal-related
        score += self._score_deal_related(text, article)

        # 3. Watchlist ticker mentions
        score += self._score_ticker_mentions(text)

        # 4. Watchlist firm mentions
        score += self._score_firm_mentions(text)

        # 5. PE/PC sponsor mentions
        score += self._score_sponsor_mentions(text)

        # 6. Recency
        score += self._score_recency(article)

        # 7. Source authority
        score += self._score_source_authority(article)

        return round(score, 2)

    def _score_sector_match(self, text: str, article: Article) -> float:
        """Award +3.0 if the article matches a primary sector."""
        points = 0.0
        matched_sectors: set[str] = set()

        for sector_name in self._primary_sectors:
            sector_cfg = self._sectors.get(sector_name, {})
            keywords = sector_cfg.get("keywords", [])
            sector_tickers = sector_cfg.get("tickers", [])

            # Check keyword match
            for kw in keywords:
                if re.search(r"\b" + re.escape(kw) + r"\b", text, re.IGNORECASE):
                    matched_sectors.add(sector_name)
                    break

            # Check if any of the article's tickers belong to this sector
            if not matched_sectors or sector_name not in matched_sectors:
                for ticker in article.tickers:
                    if ticker.upper() in [t.upper() for t in sector_tickers]:
                        matched_sectors.add(sector_name)
                        break

        points = 3.0 * len(matched_sectors)
        return points

    def _score_deal_related(self, text: str, article: Article) -> float:
        """Award +4.0 if the article is deal-related."""
        if article.is_deal_related:
            return 4.0
        if _DEAL_PATTERN.search(text):
            article.is_deal_related = True
            return 4.0
        return 0.0

    def _score_ticker_mentions(self, text: str) -> float:
        """Award +2.0 per watchlist ticker mentioned in the article."""
        points = 0.0
        for entry in self._watchlist_tickers:
            symbol = entry.get("symbol", "")
            if not symbol:
                continue
            # Match the ticker as a whole word or preceded by $
            pattern = r"(?:\$|\b)" + re.escape(symbol) + r"\b"
            if re.search(pattern, text, re.IGNORECASE):
                points += 2.0
        return points

    def _score_firm_mentions(self, text: str) -> float:
        """Award +2.5 per watchlist firm mentioned (non-sponsor firms)."""
        points = 0.0
        for firm in self._watchlist_firms:
            if firm.get("type") == "sponsor":
                continue  # scored separately
            name = firm.get("name", "")
            if not name:
                continue
            if re.search(r"\b" + re.escape(name) + r"\b", text, re.IGNORECASE):
                points += 2.5
        return points

    def _score_sponsor_mentions(self, text: str) -> float:
        """Award +3.0 per PE/PC sponsor mentioned."""
        points = 0.0
        for name in self._sponsor_names:
            if re.search(r"\b" + re.escape(name) + r"\b", text, re.IGNORECASE):
                points += 3.0
        return points

    @staticmethod
    def _score_recency(article: Article) -> float:
        """Award points based on how recently the article was published.

        - Last 6 hours:  +2.0
        - 6 - 12 hours:  +1.0
        - 12 - 24 hours: +0.5
        - Older / unknown: 0.0
        """
        if article.published is None:
            return 0.0

        now = datetime.now(tz=article.published.tzinfo)
        age_hours = (now - article.published).total_seconds() / 3600

        if age_hours < 0:
            # Future-dated article -- treat as very recent.
            return 2.0
        if age_hours <= 6:
            return 2.0
        if age_hours <= 12:
            return 1.0
        if age_hours <= 24:
            return 0.5
        return 0.0

    @staticmethod
    def _score_source_authority(article: Article) -> float:
        """Award points based on the source of the article.

        - SEC filing:  +2.0
        - PR wire:     +1.0
        - News:        +0.5
        """
        source = article.source.lower()
        if source == "sec_edgar":
            return 2.0
        if source in ("pr_newswire", "businesswire"):
            return 1.0
        return 0.5

    @staticmethod
    def _searchable_text(article: Article) -> str:
        """Build a single lowercase text blob for keyword matching."""
        return f"{article.title} {article.summary} {article.raw_content}"
