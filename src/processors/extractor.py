"""Extractor: pulls structured deal facts and classifies articles."""

import logging
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Optional

import yaml

from src.models.article import Article
from src.models.deal import Deal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Matches monetary amounts like "$1.2 billion", "$450M", "$3,200 million"
MONEY_PATTERN = re.compile(
    r"\$\s*([\d,]+(?:\.\d+)?)\s*(billion|million|B|M|bn|mn|b|m)\b",
    re.IGNORECASE,
)

# Matches valuation multiples like "12.5x EBITDA", "8x revenue"
MULTIPLE_PATTERN = re.compile(
    r"(\d+\.?\d*)\s*[xX]\s*(?:revenue|EBITDA|ARR|earnings|sales|EV/EBITDA|EV/Revenue)",
    re.IGNORECASE,
)

# Matches premium percentages like "35% premium", "premium of 42%"
PREMIUM_PATTERN = re.compile(
    r"(?:(\d+\.?\d*)\s*%\s*premium|premium\s+of\s+(\d+\.?\d*)\s*%)",
    re.IGNORECASE,
)

# Acquisition patterns: "X to acquire Y", "X agreed to buy Y", etc.
ACQUISITION_PATTERNS: list[re.Pattern] = [
    re.compile(
        r"(?P<acquirer>[A-Z][\w\s&'.,-]+?)\s+(?:to|will|has agreed to|agreed to|is set to)\s+"
        r"(?:acquire|buy|purchase|take over)\s+(?P<target>[A-Z][\w\s&'.,-]+?)(?:\s+(?:for|in)\b|\.|\,)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:acquisition|takeover|buyout)\s+of\s+(?P<target>[A-Z][\w\s&'.,-]+?)\s+"
        r"by\s+(?P<acquirer>[A-Z][\w\s&'.,-]+?)(?:\s+(?:for|in|was|is)\b|\.|\,)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<target>[A-Z][\w\s&'.,-]+?)\s+(?:to be acquired|will be acquired|is being acquired)\s+"
        r"by\s+(?P<acquirer>[A-Z][\w\s&'.,-]+?)(?:\s+(?:for|in)\b|\.|\,)",
        re.IGNORECASE,
    ),
    re.compile(
        r"merger\s+(?:of|between)\s+(?P<acquirer>[A-Z][\w\s&'.,-]+?)\s+"
        r"and\s+(?P<target>[A-Z][\w\s&'.,-]+?)(?:\s+(?:in|for|was|is|will)\b|\.|\,)",
        re.IGNORECASE,
    ),
]

# Consideration type detection
CONSIDERATION_PATTERNS: dict[str, re.Pattern] = {
    "all-cash": re.compile(r"\ball[- ]cash\b", re.IGNORECASE),
    "all-stock": re.compile(r"\ball[- ]stock\b", re.IGNORECASE),
    "cash-and-stock": re.compile(
        r"\bcash\s+and\s+stock\b|\bcash[- ]and[- ]stock\b|\bmixed\s+consideration\b",
        re.IGNORECASE,
    ),
}

# Deal type detection
DEAL_TYPE_PATTERNS: dict[str, re.Pattern] = {
    "LBO": re.compile(r"\b(?:leveraged buyout|LBO)\b", re.IGNORECASE),
    "Take-Private": re.compile(
        r"\b(?:take[- ]private|going[- ]private)\b", re.IGNORECASE
    ),
    "Merger": re.compile(r"\b(?:merger|merge)\b", re.IGNORECASE),
    "Carve-out": re.compile(
        r"\b(?:carve[- ]?out|divestiture|divest|spin[- ]?off)\b", re.IGNORECASE
    ),
    "Strategic M&A": re.compile(
        r"\b(?:acqui(?:re|sition)|buyout|takeover|buy)\b", re.IGNORECASE
    ),
}

# Deal status detection
STATUS_PATTERNS: dict[str, re.Pattern] = {
    "completed": re.compile(
        r"\b(?:completed|closed|finalized|consummated)\b", re.IGNORECASE
    ),
    "terminated": re.compile(
        r"\b(?:terminated|called off|abandoned|withdrawn|collapsed)\b",
        re.IGNORECASE,
    ),
    "pending": re.compile(
        r"\b(?:pending|awaiting|regulatory approval|antitrust review)\b",
        re.IGNORECASE,
    ),
    "announced": re.compile(
        r"\b(?:announced|definitive agreement|signed)\b", re.IGNORECASE
    ),
    "rumored": re.compile(
        r"\b(?:rumor|reportedly|exploring|consider|potential|may|could)\b",
        re.IGNORECASE,
    ),
}

# Ticker pattern: matches $AAPL style or standalone known tickers
TICKER_DOLLAR_PATTERN = re.compile(r"\$([A-Z]{1,5})\b")

# Sponsor / seller patterns
SPONSOR_PATTERN = re.compile(
    r"(?:backed by|portfolio company of|sponsor(?:ed)?(?:\s+by)?|owned by)\s+"
    r"(?P<sponsor>[A-Z][\w\s&'.,-]+?)(?:\s*[,.]|\s+(?:and|will|has|is)\b)",
    re.IGNORECASE,
)

SELLER_PATTERN = re.compile(
    r"(?:sold by|divested by|(?:being )?sold\s+(?:by|from))\s+"
    r"(?P<seller>[A-Z][\w\s&'.,-]+?)(?:\s*[,.]|\s+(?:to|for|in)\b)",
    re.IGNORECASE,
)


def _parse_money(text: str) -> Optional[float]:
    """Extract the first monetary value in *text* as millions (float).

    Returns None if no match is found.
    """
    match = MONEY_PATTERN.search(text)
    if not match:
        return None

    raw_number = float(match.group(1).replace(",", ""))
    unit = match.group(2).lower()

    if unit in ("billion", "b", "bn"):
        return raw_number * 1000  # convert to millions
    # million, m, mn
    return raw_number


class Extractor:
    """Extract structured deal information and classify articles."""

    def __init__(self, config_path: str = "config"):
        self._config_dir = Path(config_path)
        self._sector_config: dict[str, Any] = {}
        self._known_tickers: set[str] = set()
        self._sponsor_names: list[str] = []
        self._load_configs()

    # ------------------------------------------------------------------
    # Config loading
    # ------------------------------------------------------------------

    def _load_configs(self) -> None:
        sectors_path = self._config_dir / "sectors.yaml"
        watchlist_path = self._config_dir / "watchlist.yaml"

        if sectors_path.exists():
            with open(sectors_path, "r") as fh:
                self._sector_config = yaml.safe_load(fh) or {}

        if watchlist_path.exists():
            with open(watchlist_path, "r") as fh:
                wl = yaml.safe_load(fh) or {}
            for entry in wl.get("tickers", []):
                symbol = entry.get("symbol", "")
                if symbol:
                    self._known_tickers.add(symbol.upper())
            for firm in wl.get("firms", []):
                if firm.get("type") == "sponsor":
                    self._sponsor_names.append(firm["name"])

    # ------------------------------------------------------------------
    # Deal extraction
    # ------------------------------------------------------------------

    def extract_deals(self, articles: list[Article]) -> list[Deal]:
        """Extract deal facts from deal-related articles.

        Articles about the same deal (matched by target+acquirer) are grouped
        together, and their facts are merged.  No data is fabricated -- fields
        that cannot be extracted remain as their default (None or empty string).
        """
        deal_articles = [a for a in articles if a.is_deal_related]
        if not deal_articles:
            return []

        # Map (normalised_target, normalised_acquirer) -> list of articles
        deal_groups: dict[tuple[str, str], list[Article]] = defaultdict(list)

        for article in deal_articles:
            text = self._full_text(article)
            parties = self._extract_parties(text)
            target = parties.get("target", "")
            acquirer = parties.get("acquirer", "")

            if not target and not acquirer:
                # Cannot determine parties -- skip grouping, process solo
                target = article.title  # fallback key
                acquirer = ""

            key = (self._normalise(target), self._normalise(acquirer))
            deal_groups[key].append(article)

        deals: list[Deal] = []
        for (_target_key, _acquirer_key), group in deal_groups.items():
            deal = self._build_deal(group)
            if deal is not None:
                deals.append(deal)

        logger.info("Extracted %d deals from %d articles", len(deals), len(deal_articles))
        return deals

    def _build_deal(self, articles: list[Article]) -> Optional[Deal]:
        """Merge information from a group of articles into a single Deal."""
        combined_text = " ".join(self._full_text(a) for a in articles)

        parties = self._extract_parties(combined_text)
        financials = self._extract_financials(combined_text)

        target = parties.get("target", "").strip()
        acquirer = parties.get("acquirer", "").strip()

        if not target and not acquirer:
            return None

        # Deal type -- first match wins (ordered by specificity)
        deal_type = ""
        for dtype, pattern in DEAL_TYPE_PATTERNS.items():
            if pattern.search(combined_text):
                deal_type = dtype
                break

        # Consideration
        consideration = ""
        for ctype, pattern in CONSIDERATION_PATTERNS.items():
            if pattern.search(combined_text):
                consideration = ctype
                break

        # Status -- first match wins (ordered from most definitive)
        status = "rumored"
        for sname, pattern in STATUS_PATTERNS.items():
            if pattern.search(combined_text):
                status = sname
                break

        # Sponsor & seller
        sponsor = parties.get("sponsor", "")
        seller = parties.get("seller", "")

        # Sector from articles
        sectors = set()
        for a in articles:
            sectors.update(a.sectors)
        sector = sorted(sectors)[0] if sectors else ""

        deal = Deal(
            target=target or "Unknown",
            acquirer=acquirer or "Unknown",
            deal_type=deal_type,
            ev_mm=financials.get("ev_mm"),
            equity_value_mm=financials.get("equity_value_mm"),
            ev_revenue=financials.get("ev_revenue"),
            ev_ebitda=financials.get("ev_ebitda"),
            premium_pct=financials.get("premium_pct"),
            consideration=consideration,
            status=status,
            announced_date=date.today() if status == "announced" else None,
            sector=sector,
            source_articles=[a.id for a in articles],
            seller=seller,
            sponsor=sponsor,
        )
        return deal

    # ------------------------------------------------------------------
    # Party extraction
    # ------------------------------------------------------------------

    def _extract_parties(self, text: str) -> dict[str, str]:
        """Extract buyer, target, seller, sponsor from *text* via regex."""
        result: dict[str, str] = {
            "target": "",
            "acquirer": "",
            "seller": "",
            "sponsor": "",
        }

        for pattern in ACQUISITION_PATTERNS:
            match = pattern.search(text)
            if match:
                groups = match.groupdict()
                result["target"] = groups.get("target", "").strip().rstrip(".,;")
                result["acquirer"] = groups.get("acquirer", "").strip().rstrip(".,;")
                break

        # Sponsor
        sponsor_match = SPONSOR_PATTERN.search(text)
        if sponsor_match:
            result["sponsor"] = sponsor_match.group("sponsor").strip().rstrip(".,;")
        else:
            # Check against known sponsor names
            for name in self._sponsor_names:
                if re.search(r"\b" + re.escape(name) + r"\b", text, re.IGNORECASE):
                    result["sponsor"] = name
                    break

        # Seller
        seller_match = SELLER_PATTERN.search(text)
        if seller_match:
            result["seller"] = seller_match.group("seller").strip().rstrip(".,;")

        return result

    # ------------------------------------------------------------------
    # Financial extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_financials(text: str) -> dict[str, Any]:
        """Extract EV, equity value, multiples, and premium from *text*.

        Returns a dict with keys: ev_mm, equity_value_mm, ev_revenue,
        ev_ebitda, premium_pct.  Values are None when not found.
        """
        result: dict[str, Any] = {
            "ev_mm": None,
            "equity_value_mm": None,
            "ev_revenue": None,
            "ev_ebitda": None,
            "premium_pct": None,
        }

        # --- Enterprise / equity value ---
        # Look for "enterprise value of $X" or "valued at $X" or "for $X"
        ev_match = re.search(
            r"(?:enterprise\s+value|EV)\s+(?:of\s+)?" + MONEY_PATTERN.pattern,
            text,
            re.IGNORECASE,
        )
        if ev_match:
            result["ev_mm"] = _parse_money(ev_match.group(0))

        equity_match = re.search(
            r"(?:equity\s+value|market\s+cap(?:italization)?)\s+(?:of\s+)?"
            + MONEY_PATTERN.pattern,
            text,
            re.IGNORECASE,
        )
        if equity_match:
            result["equity_value_mm"] = _parse_money(equity_match.group(0))

        # If neither explicit label found, use the first monetary value as EV
        if result["ev_mm"] is None and result["equity_value_mm"] is None:
            generic_val = _parse_money(text)
            if generic_val is not None:
                result["ev_mm"] = generic_val

        # --- Multiples ---
        for mult_match in MULTIPLE_PATTERN.finditer(text):
            multiple_str = f"{mult_match.group(1)}x"
            metric = mult_match.group(0).lower()
            if "ebitda" in metric:
                result["ev_ebitda"] = result["ev_ebitda"] or multiple_str
            elif any(k in metric for k in ("revenue", "sales", "arr")):
                result["ev_revenue"] = result["ev_revenue"] or multiple_str

        # --- Premium ---
        premium_match = PREMIUM_PATTERN.search(text)
        if premium_match:
            pct_str = premium_match.group(1) or premium_match.group(2)
            if pct_str:
                result["premium_pct"] = float(pct_str)

        return result

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def classify_sectors(
        self, articles: list[Article], sector_config: Optional[dict] = None
    ) -> list[Article]:
        """Assign sector tags to articles based on keyword matching.

        Uses the provided *sector_config* or falls back to the config loaded
        from sectors.yaml.
        """
        config = sector_config or self._sector_config

        for article in articles:
            text = self._full_text(article).lower()
            matched: set[str] = set(article.sectors)

            for sector_name, sector_def in config.items():
                keywords = sector_def.get("keywords", [])
                sector_tickers = [t.upper() for t in sector_def.get("tickers", [])]

                # Keyword match
                for kw in keywords:
                    if re.search(r"\b" + re.escape(kw.lower()) + r"\b", text):
                        matched.add(sector_name)
                        break

                # Ticker match
                for ticker in article.tickers:
                    if ticker.upper() in sector_tickers:
                        matched.add(sector_name)
                        break

            article.sectors = sorted(matched)

        return articles

    def extract_tickers(self, articles: list[Article]) -> list[Article]:
        """Find stock ticker mentions in article text.

        Detects both $TICKER patterns and bare ticker symbols that appear in the
        watchlist.  Results are merged with any tickers already on the article.
        """
        for article in articles:
            text = self._full_text(article)
            found: set[str] = set(article.tickers)

            # $TICKER mentions
            for match in TICKER_DOLLAR_PATTERN.finditer(text):
                found.add(match.group(1).upper())

            # Known watchlist tickers as whole words
            for ticker in self._known_tickers:
                # Require word boundary to avoid false positives for short
                # tickers like "C", "T" -- only match uppercase in the raw text
                # for single-char tickers.
                if len(ticker) <= 2:
                    # Require exact uppercase surrounded by non-alpha to reduce
                    # false positives for very short symbols.
                    pattern = r"(?<![A-Za-z])" + re.escape(ticker) + r"(?![A-Za-z])"
                    if re.search(pattern, article.title + " " + article.summary):
                        found.add(ticker)
                else:
                    pattern = r"\b" + re.escape(ticker) + r"\b"
                    if re.search(pattern, text, re.IGNORECASE):
                        found.add(ticker.upper())

            article.tickers = sorted(found)

        return articles

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _full_text(article: Article) -> str:
        return f"{article.title} {article.summary} {article.raw_content}"

    @staticmethod
    def _normalise(name: str) -> str:
        """Lowercase, strip punctuation, collapse whitespace."""
        name = name.lower().strip()
        name = re.sub(r"[^a-z0-9\s]", "", name)
        name = re.sub(r"\s+", " ", name)
        return name
