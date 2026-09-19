"""Verifier: cross-source verification and data quality checks."""

import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Optional

from src.models.article import Article
from src.models.deal import Deal
from src.models.market_snapshot import MarketSnapshot

logger = logging.getLogger(__name__)

# Valid deal statuses
VALID_STATUSES = frozenset({
    "rumored", "announced", "pending", "completed", "terminated",
})

# Reasonable ranges for sanity checks
MULTIPLE_MIN = 0.5
MULTIPLE_MAX = 100.0

INDEX_RANGES: dict[str, tuple[float, float]] = {
    "SP500": (500, 15000),
    "NASDAQ": (1000, 40000),
    "DJIA": (5000, 100000),
    "Russell2000": (300, 10000),
}

YIELD_MAX = 20.0  # percent
VIX_MAX = 100.0
MAX_DATA_AGE_HOURS = 20.0


class Verifier:
    """Cross-source verification and data-quality checks.

    Never fabricates missing data.  Fields that cannot be verified or that
    fail checks are flagged (via logging / metadata) but not silently altered.
    """

    # ------------------------------------------------------------------
    # Article verification
    # ------------------------------------------------------------------

    def verify_articles(self, articles: list[Article]) -> list[Article]:
        """Flag articles that lack cross-source corroboration.

        Articles whose core story (identified by similar title) appears from
        multiple independent sources receive a confidence boost.  Single-source
        stories receive a penalty so that they rank lower without being removed.
        """
        if not articles:
            return articles

        # Group articles by normalised title prefix (first 60 chars, lowered)
        # to detect stories covered by multiple outlets.
        story_groups: dict[str, list[Article]] = defaultdict(list)
        for article in articles:
            key = self._story_key(article)
            story_groups[key].append(article)

        for key, group in story_groups.items():
            unique_sources = {a.source for a in group}
            multi_source = len(unique_sources) > 1

            for article in group:
                if multi_source:
                    # Corroborated by at least two independent sources
                    article.relevance_score += 1.0
                    logger.debug(
                        "Boosted '%s' (+1.0): corroborated by %d sources",
                        article.title[:60],
                        len(unique_sources),
                    )
                else:
                    # Single-source story -- lower confidence
                    article.relevance_score = max(
                        0.0, article.relevance_score - 0.5
                    )
                    logger.debug(
                        "Penalised '%s' (-0.5): single-source story",
                        article.title[:60],
                    )

        return articles

    # ------------------------------------------------------------------
    # Deal verification
    # ------------------------------------------------------------------

    def verify_deal(self, deal: Deal) -> Deal:
        """Sanity-check deal data.  Returns the deal with warnings logged.

        Checks:
        - EV vs equity value are not confused (EV should >= equity value)
        - Multiples are in a reasonable range (0.5x - 100x)
        - Status is one of the valid values
        - Dates make sense (announced_date not in the far future)
        - Never fabricates missing data (None stays None)
        """
        warnings: list[str] = []

        # --- EV vs equity value ---
        if (
            deal.ev_mm is not None
            and deal.equity_value_mm is not None
            and deal.ev_mm < deal.equity_value_mm
        ):
            warnings.append(
                f"EV (${deal.ev_mm:.1f}M) is less than equity value "
                f"(${deal.equity_value_mm:.1f}M) -- possible confusion"
            )

        # --- Multiples ---
        for label, value_str in [
            ("EV/Revenue", deal.ev_revenue),
            ("EV/EBITDA", deal.ev_ebitda),
        ]:
            if value_str is not None:
                parsed = self._parse_multiple(value_str)
                if parsed is not None and not (MULTIPLE_MIN <= parsed <= MULTIPLE_MAX):
                    warnings.append(
                        f"{label} multiple {value_str} outside reasonable range "
                        f"({MULTIPLE_MIN}x - {MULTIPLE_MAX}x)"
                    )

        # --- Status ---
        if deal.status not in VALID_STATUSES:
            warnings.append(
                f"Invalid deal status '{deal.status}'; "
                f"valid values: {', '.join(sorted(VALID_STATUSES))}"
            )
            # Normalise to closest match or default
            deal.status = self._closest_status(deal.status)

        # --- Dates ---
        if deal.announced_date is not None:
            today = datetime.now().date()
            # Announced date more than 7 days in the future is suspicious
            if deal.announced_date > today + timedelta(days=7):
                warnings.append(
                    f"Announced date {deal.announced_date} is more than 7 days "
                    "in the future"
                )
            # Announced date more than 5 years in the past is suspicious
            if deal.announced_date < today - timedelta(days=5 * 365):
                warnings.append(
                    f"Announced date {deal.announced_date} is more than 5 years "
                    "in the past"
                )

        # --- Premium ---
        if deal.premium_pct is not None:
            if deal.premium_pct < 0:
                warnings.append(
                    f"Negative premium ({deal.premium_pct}%) is unusual"
                )
            if deal.premium_pct > 200:
                warnings.append(
                    f"Premium of {deal.premium_pct}% is unusually high"
                )

        # --- EV sanity ---
        if deal.ev_mm is not None and deal.ev_mm <= 0:
            warnings.append(f"EV is non-positive (${deal.ev_mm:.1f}M)")

        for w in warnings:
            logger.warning("Deal '%s -> %s': %s", deal.target, deal.acquirer, w)

        return deal

    # ------------------------------------------------------------------
    # Market data verification
    # ------------------------------------------------------------------

    def verify_market_data(self, snapshot: MarketSnapshot) -> MarketSnapshot:
        """Check market data freshness and sanity.

        Flags:
        - Data older than 20 hours
        - Index levels outside reasonable ranges
        - Yields negative or above 20%
        - VIX negative or above 100
        """
        warnings: list[str] = []

        # --- Freshness ---
        if snapshot.is_stale(max_age_hours=MAX_DATA_AGE_HOURS):
            age_hours = (
                datetime.now() - snapshot.timestamp
            ).total_seconds() / 3600
            warnings.append(
                f"Market data is {age_hours:.1f}h old (threshold: {MAX_DATA_AGE_HOURS}h)"
            )

        # --- Index levels ---
        for name, level in snapshot.indices.items():
            if level is None:
                continue
            expected = INDEX_RANGES.get(name)
            if expected and not (expected[0] <= level <= expected[1]):
                warnings.append(
                    f"Index {name} level {level:,.2f} outside expected range "
                    f"[{expected[0]:,.0f} - {expected[1]:,.0f}]"
                )

        # --- Yields ---
        for tenor, yld in snapshot.yields.items():
            if yld is None:
                continue
            if yld < 0:
                warnings.append(f"Yield {tenor} is negative ({yld:.3f}%)")
            if yld > YIELD_MAX:
                warnings.append(
                    f"Yield {tenor} ({yld:.3f}%) exceeds {YIELD_MAX}%"
                )

        # --- VIX ---
        if snapshot.vix is not None:
            if snapshot.vix < 0:
                warnings.append(f"VIX is negative ({snapshot.vix:.2f})")
            if snapshot.vix > VIX_MAX:
                warnings.append(
                    f"VIX ({snapshot.vix:.2f}) exceeds {VIX_MAX}"
                )

        # --- Rates ---
        for name, rate in snapshot.rates.items():
            if rate is not None and rate < 0:
                warnings.append(f"Rate {name} is negative ({rate:.4f}%)")

        for w in warnings:
            logger.warning("Market data: %s", w)

        return snapshot

    # ------------------------------------------------------------------
    # Conflict detection
    # ------------------------------------------------------------------

    def check_conflicts(self, articles: list[Article]) -> list[dict[str, Any]]:
        """Detect conflicting facts between articles about the same deal.

        When articles about the same deal disagree on key facts (deal size,
        status, acquirer), return a list of conflict descriptions for the LLM
        to note in the briefing.
        """
        if not articles:
            return []

        deal_articles = [a for a in articles if a.is_deal_related]
        if not deal_articles:
            return []

        # Group by story key
        story_groups: dict[str, list[Article]] = defaultdict(list)
        for article in deal_articles:
            key = self._story_key(article)
            story_groups[key].append(article)

        conflicts: list[dict[str, Any]] = []

        for key, group in story_groups.items():
            if len(group) < 2:
                continue

            group_conflicts = self._detect_group_conflicts(group)
            conflicts.extend(group_conflicts)

        if conflicts:
            logger.info("Detected %d fact conflicts across deal articles", len(conflicts))

        return conflicts

    def _detect_group_conflicts(
        self, group: list[Article]
    ) -> list[dict[str, Any]]:
        """Compare articles in a group for factual disagreements."""
        conflicts: list[dict[str, Any]] = []
        texts = [(a, f"{a.title} {a.summary} {a.raw_content}") for a in group]

        # --- Deal size conflicts ---
        amounts: list[tuple[Article, float]] = []
        for article, text in texts:
            match = re.search(
                r"\$\s*([\d,]+(?:\.\d+)?)\s*(billion|million|B|M|bn|mn|b|m)\b",
                text,
                re.IGNORECASE,
            )
            if match:
                raw = float(match.group(1).replace(",", ""))
                unit = match.group(2).lower()
                if unit in ("billion", "b", "bn"):
                    raw *= 1000
                amounts.append((article, raw))

        if len(amounts) >= 2:
            values = [v for _, v in amounts]
            min_val, max_val = min(values), max(values)
            # Flag if discrepancy exceeds 10% of the larger value
            if max_val > 0 and (max_val - min_val) / max_val > 0.10:
                conflicts.append({
                    "type": "deal_size",
                    "story": group[0].title[:80],
                    "values": [
                        {
                            "source": a.source,
                            "title": a.title[:80],
                            "amount_mm": v,
                        }
                        for a, v in amounts
                    ],
                    "description": (
                        f"Deal size discrepancy: "
                        f"${min_val:,.0f}M vs ${max_val:,.0f}M"
                    ),
                })

        # --- Status conflicts ---
        statuses: dict[str, list[Article]] = defaultdict(list)
        for article, text in texts:
            for status, pattern in [
                ("completed", re.compile(r"\b(?:completed|closed|finalized)\b", re.I)),
                ("terminated", re.compile(r"\b(?:terminated|called off|abandoned)\b", re.I)),
                ("pending", re.compile(r"\b(?:pending|awaiting approval)\b", re.I)),
                ("announced", re.compile(r"\b(?:announced|definitive agreement)\b", re.I)),
                ("rumored", re.compile(r"\b(?:rumored|reportedly|exploring)\b", re.I)),
            ]:
                if pattern.search(text):
                    statuses[status].append(article)
                    break

        unique_statuses = set(statuses.keys())
        # Conflicting statuses (e.g., one says "completed", another says "rumored")
        if len(unique_statuses) > 1:
            # Not all combinations are true conflicts. E.g. "announced" and
            # "pending" can coexist.  Flag only genuinely contradictory pairs.
            contradictions = {
                frozenset({"completed", "rumored"}),
                frozenset({"completed", "terminated"}),
                frozenset({"terminated", "announced"}),
                frozenset({"terminated", "pending"}),
            }
            for pair in contradictions:
                if pair.issubset(unique_statuses):
                    statuses_str = " vs ".join(sorted(pair))
                    conflicts.append({
                        "type": "deal_status",
                        "story": group[0].title[:80],
                        "statuses": {
                            s: [a.source for a in arts]
                            for s, arts in statuses.items()
                            if s in pair
                        },
                        "description": f"Deal status conflict: {statuses_str}",
                    })

        return conflicts

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _story_key(article: Article) -> str:
        """Generate a normalised key for grouping articles about the same story.

        Uses the first 60 characters of the lowercased title, stripped of
        punctuation and extra whitespace.
        """
        key = article.title.lower()[:60]
        key = re.sub(r"[^a-z0-9\s]", "", key)
        key = re.sub(r"\s+", " ", key).strip()
        return key

    @staticmethod
    def _parse_multiple(value: str) -> Optional[float]:
        """Parse a multiple string like '12.5x' into a float."""
        match = re.match(r"(\d+\.?\d*)\s*x?", value, re.IGNORECASE)
        if match:
            return float(match.group(1))
        return None

    @staticmethod
    def _closest_status(raw: str) -> str:
        """Map an invalid status string to the closest valid one."""
        raw_lower = raw.lower().strip()
        for valid in VALID_STATUSES:
            if valid in raw_lower or raw_lower in valid:
                return valid
        return "rumored"  # safe default
