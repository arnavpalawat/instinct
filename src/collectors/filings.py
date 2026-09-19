"""SEC EDGAR filings collector using the full-text search API."""
import logging
import time
from datetime import datetime, timedelta
from typing import Optional

import requests

from src.models.article import Article

logger = logging.getLogger(__name__)

# EDGAR asks that automated tools be polite: max 10 requests/second.
_EDGAR_REQUEST_INTERVAL = 0.5  # seconds between requests


class FilingsCollector:
    """Collects recent SEC filings from EDGAR full-text search and RSS."""

    SEARCH_BASE_URL = "https://efts.sec.gov/LATEST/search-index"
    FILING_BASE_URL = "https://www.sec.gov/Archives/edgar/data"

    DEFAULT_QUERIES = [
        "merger agreement",
        "acquisition",
        "definitive agreement",
    ]

    DEFAULT_FORM_TYPES = ["8-K", "S-1"]

    def __init__(self, config: dict):
        self.config = config
        self.headers = {
            "User-Agent": "Instinct Financial Briefing contact@example.com",
            "Accept": "application/json",
        }
        self._last_request_time: float = 0.0

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def collect(self, queries: Optional[list[str]] = None) -> list[Article]:
        """Search EDGAR for recent filings matching deal-related queries.

        Args:
            queries: Search terms. Defaults to merger/acquisition related terms.

        Returns:
            De-duplicated list of Article objects for matching filings.
        """
        if queries is None:
            queries = self.DEFAULT_QUERIES

        articles: list[Article] = []
        seen_ids: set[str] = set()

        def _add(batch: list[Article]) -> None:
            for a in batch:
                if a.id not in seen_ids:
                    seen_ids.add(a.id)
                    articles.append(a)

        # Full-text search for each query
        for query in queries:
            _add(self._search_edgar(query, filing_types=self.DEFAULT_FORM_TYPES))

        # Also fetch recent 8-K filings
        _add(self._fetch_recent_8k())

        logger.info("EDGAR filing collection complete: %d filings", len(articles))
        return articles

    # ------------------------------------------------------------------
    # EDGAR full-text search
    # ------------------------------------------------------------------

    def _search_edgar(
        self,
        query: str,
        filing_types: Optional[list[str]] = None,
    ) -> list[Article]:
        """Search the EDGAR full-text search index for a given query.

        Uses the endpoint:
            https://efts.sec.gov/LATEST/search-index?q=...&forms=...&dateRange=custom&startdt=...&enddt=...
        """
        articles: list[Article] = []
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        params: dict = {
            "q": f'"{query}"',
            "dateRange": "custom",
            "startdt": yesterday,
            "enddt": today,
        }
        if filing_types:
            params["forms"] = ",".join(filing_types)

        try:
            self._rate_limit()
            response = requests.get(
                self.SEARCH_BASE_URL,
                params=params,
                headers=self.headers,
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

            hits = data.get("hits", {}).get("hits", [])
            for hit in hits:
                try:
                    source = hit.get("_source", {})
                    file_num = source.get("file_num", "")
                    form_type = source.get("form_type", "")
                    entity_name = source.get("entity_name", "")
                    file_date = source.get("file_date", "")
                    display_names = source.get("display_names", [])

                    # Build a readable title
                    filer = entity_name or (display_names[0] if display_names else "Unknown")
                    title = f"{form_type}: {filer}"

                    # Construct URL to filing
                    accession = source.get("accession_no", "").replace("-", "")
                    cik = source.get("cik", "")
                    if accession and cik:
                        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}"
                    else:
                        url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&filenum={file_num}"

                    published = None
                    if file_date:
                        try:
                            published = datetime.strptime(file_date, "%Y-%m-%d")
                        except ValueError:
                            pass

                    tickers_list = []
                    tickers_raw = source.get("tickers", "")
                    if tickers_raw:
                        tickers_list = [
                            t.strip() for t in tickers_raw.split(",") if t.strip()
                        ]

                    articles.append(Article(
                        title=title,
                        url=url,
                        source="sec_edgar",
                        published=published,
                        summary=f"{form_type} filed by {filer} on {file_date}. Query match: {query}",
                        tickers=tickers_list,
                        is_deal_related=True,
                    ))
                except Exception as exc:
                    logger.debug("Failed to parse EDGAR search hit: %s", exc)

        except requests.exceptions.RequestException as exc:
            logger.error("EDGAR search request failed for query '%s': %s", query, exc)
        except Exception as exc:
            logger.error("EDGAR search processing failed for query '%s': %s", query, exc)

        return articles

    # ------------------------------------------------------------------
    # Recent 8-K filings
    # ------------------------------------------------------------------

    def _fetch_recent_8k(self) -> list[Article]:
        """Fetch recent 8-K filings via the EDGAR full-text search API.

        8-K filings disclose material events such as acquisitions, executive
        changes, and other significant corporate actions.
        """
        articles: list[Article] = []
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        params: dict = {
            "forms": "8-K",
            "dateRange": "custom",
            "startdt": yesterday,
            "enddt": today,
        }

        try:
            self._rate_limit()
            response = requests.get(
                self.SEARCH_BASE_URL,
                params=params,
                headers=self.headers,
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

            hits = data.get("hits", {}).get("hits", [])
            for hit in hits:
                try:
                    source = hit.get("_source", {})
                    entity_name = source.get("entity_name", "")
                    display_names = source.get("display_names", [])
                    file_date = source.get("file_date", "")
                    form_type = source.get("form_type", "8-K")

                    filer = entity_name or (display_names[0] if display_names else "Unknown")
                    title = f"{form_type}: {filer}"

                    accession = source.get("accession_no", "").replace("-", "")
                    cik = source.get("cik", "")
                    if accession and cik:
                        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}"
                    else:
                        file_num = source.get("file_num", "")
                        url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&filenum={file_num}"

                    published = None
                    if file_date:
                        try:
                            published = datetime.strptime(file_date, "%Y-%m-%d")
                        except ValueError:
                            pass

                    tickers_list = []
                    tickers_raw = source.get("tickers", "")
                    if tickers_raw:
                        tickers_list = [
                            t.strip() for t in tickers_raw.split(",") if t.strip()
                        ]

                    # Determine deal relevance from items reported
                    items = source.get("items", "")
                    is_deal = any(
                        kw in (items or "").lower()
                        for kw in ["acquisition", "merger", "asset", "business combination"]
                    )

                    articles.append(Article(
                        title=title,
                        url=url,
                        source="sec_edgar",
                        published=published,
                        summary=f"{form_type} filed by {filer} on {file_date}",
                        tickers=tickers_list,
                        is_deal_related=is_deal,
                    ))
                except Exception as exc:
                    logger.debug("Failed to parse 8-K filing: %s", exc)

        except requests.exceptions.RequestException as exc:
            logger.error("EDGAR 8-K fetch failed: %s", exc)
        except Exception as exc:
            logger.error("EDGAR 8-K processing failed: %s", exc)

        return articles

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _rate_limit(self) -> None:
        """Enforce minimum delay between EDGAR requests to be polite."""
        elapsed = time.time() - self._last_request_time
        if elapsed < _EDGAR_REQUEST_INTERVAL:
            time.sleep(_EDGAR_REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.time()
