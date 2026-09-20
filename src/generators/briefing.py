"""Per-section briefing generation using prompt templates and LLM."""

import logging
from datetime import datetime

from jinja2 import Environment, FileSystemLoader

from src.generators.llm_client import LLMClient
from src.generators.deal_analyzer import DealAnalyzer
from src.generators.interview_prep import InterviewPrepGenerator
from src.models.briefing import Briefing
from src.models.market_snapshot import MarketSnapshot
from src.models.article import Article
from src.models.deal import Deal

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a financial briefing writer for Instinct, a daily briefing "
    "that helps candidates preparing for Investment Banking, Private Equity, and "
    "Private Credit recruiting interviews stay current on markets and deals. "
    "Write in a professional but conversational tone. Output HTML: use <p> for "
    "paragraphs, <a href> for source links, <strong> for emphasis, and <ul>/<li> "
    "for lists where appropriate. "
    "Be concise, precise, and analytically sharp. Never fabricate financial data — "
    "if data is unavailable, say so. Label all hypothetical assumptions clearly."
)


class BriefingGenerator:
    """Generates a complete daily briefing by rendering prompt templates
    and calling an LLM for each section."""

    SECTION_CONFIGS = {
        "opening_brief": {"target_words": 450, "priority": 1},
        "markets_macro": {"target_words": 650, "priority": 2},
        "deal_of_day": {"target_words": 900, "priority": 3},
        "pe_pc": {"target_words": 750, "priority": 4},
        "company_insight": {"target_words": 650, "priority": 5},
        "politics_policy": {"target_words": 400, "priority": 6},
        "interview_practice": {"target_words": 600, "priority": 7},
        "what_to_watch": {"target_words": 450, "priority": 8},
    }

    def __init__(self, llm: LLMClient, config: dict):
        self.llm = llm
        self.config = config
        self.deal_analyzer = DealAnalyzer(llm)
        self.interview_prep = InterviewPrepGenerator(llm)
        try:
            self.prompt_env = Environment(
                loader=FileSystemLoader("config/prompts"),
                undefined=__import__("jinja2").Undefined,
            )
        except Exception as exc:
            logger.warning("Failed to load prompt templates: %s", exc)
            self.prompt_env = None

    def generate(
        self,
        market: MarketSnapshot,
        articles: list[Article],
        deals: list[Deal],
        **kwargs,
    ) -> Briefing:
        """Generate the complete briefing — all 7 sections plus appendix."""
        briefing = Briefing()
        briefing.market_snapshot = market.to_dict()
        briefing.info_cutoff = datetime.now()

        self._generate_weekday(briefing, market, articles, deals)

        briefing.compute_word_count()
        briefing.headline = self._generate_headline(briefing)

        # Store deal references
        briefing.deals = [d.to_dict() for d in deals[:5]]

        logger.info(
            "Briefing generated: %d words, %d sections filled",
            briefing.word_count,
            sum(1 for v in briefing.sections.values() if v),
        )
        return briefing

    # ── Weekday generation ──────────────────────────────────────────────

    def _generate_weekday(
        self,
        briefing: Briefing,
        market: MarketSnapshot,
        articles: list[Article],
        deals: list[Deal],
    ):
        """Generate all 7 sections for a weekday briefing."""
        # Select the featured deal (highest priority: most recent announced deal
        # with the most source coverage)
        featured_deal = self._select_featured_deal(deals)
        deal_analysis = {}
        interview_content = {}

        # Pre-generate deal analysis if we have a featured deal
        if featured_deal:
            deal_articles = [
                a
                for a in articles
                if a.id in featured_deal.source_articles or a.is_deal_related
            ]
            try:
                deal_analysis = self.deal_analyzer.analyze(
                    featured_deal, deal_articles
                )
            except Exception as exc:
                logger.error("Deal analysis failed: %s", exc)
                briefing.pipeline_errors.append(f"deal_analysis: {exc}")

            # Generate interview prep content
            try:
                interview_content = self.interview_prep.generate(
                    featured_deal, deal_analysis, market, articles
                )
            except Exception as exc:
                logger.error("Interview prep generation failed: %s", exc)
                briefing.pipeline_errors.append(f"interview_prep: {exc}")

        # Categorize articles
        macro_articles = [
            a
            for a in articles
            if any(
                kw in (a.title + a.summary).lower()
                for kw in [
                    "fed", "inflation", "gdp", "jobs", "employment", "cpi",
                    "fomc", "treasury", "rates", "economic", "macro",
                ]
            )
        ]
        pe_pc_articles = [
            a
            for a in articles
            if any(
                kw in (a.title + a.summary).lower()
                for kw in [
                    "private equity", "private credit", "buyout", "lbo",
                    "leveraged", "sponsor", "fund", "pe ", "pc ",
                    "direct lending", "mezzanine",
                ]
            )
        ]
        pe_pc_deals = [
            d
            for d in deals
            if d.deal_type
            in ("LBO", "Take-Private", "Carve-out")
            or d.sponsor
        ]

        # Select a company for the insight section
        company_articles = self._select_company_articles(
            articles, featured_deal
        )
        watchlist_items = market.watchlist[:5]

        # Politics/policy articles
        politics_articles = [
            a
            for a in articles
            if "politics" in a.sectors
            or any(
                kw in (a.title + a.summary).lower()
                for kw in [
                    "policy", "regulation", "regulatory", "tariff",
                    "federal reserve", "fiscal", "antitrust", "sanctions",
                    "geopolit", "congress", "legislation", "trade war",
                ]
            )
        ]

        # Forward-looking articles
        forward_articles = [
            a
            for a in articles
            if any(
                kw in (a.title + a.summary).lower()
                for kw in [
                    "outlook", "preview", "expect", "upcoming", "next week",
                    "tomorrow", "watch for", "catalyst",
                ]
            )
        ]
        pending_deals = [
            d for d in deals if d.status in ("announced", "pending", "rumored")
        ]

        # Generate each section
        section_data = {
            "opening_brief": {
                "market_data": market.to_dict(),
                "articles": articles[:5],
                "deals": deals[:3],
            },
            "markets_macro": {
                "market_data": market.to_dict(),
                "macro_articles": macro_articles[:4],
            },
            "deal_of_day": {
                "deal": featured_deal,
                "deal_analysis": deal_analysis,
                "deal_articles": (
                    [
                        a
                        for a in articles
                        if a.is_deal_related
                        or (
                            featured_deal
                            and a.id in featured_deal.source_articles
                        )
                    ][:5]
                    if featured_deal
                    else []
                ),
            },
            "pe_pc": {
                "pe_pc_articles": pe_pc_articles[:6],
                "pe_pc_deals": pe_pc_deals[:4],
                "market_data": market.to_dict(),
            },
            "company_insight": {
                "company_articles": company_articles[:4],
                "watchlist_items": [w.to_dict() for w in watchlist_items],
            },
            "politics_policy": {
                "politics_articles": politics_articles[:6],
            },
            "interview_practice": {
                "deal": featured_deal,
                "interview_content": interview_content,
                "market_data": market.to_dict(),
            },
            "what_to_watch": {
                "forward_articles": forward_articles[:4],
                "pending_deals": pending_deals[:3],
                "market_data": market.to_dict(),
            },
        }

        for section, cfg in sorted(
            self.SECTION_CONFIGS.items(), key=lambda x: x[1]["priority"]
        ):
            try:
                data = section_data.get(section, {})
                data["date"] = briefing.date
                data["target_words"] = cfg["target_words"]
                text = self._generate_section(section, data, cfg)
                briefing.sections[section] = text
                logger.info(
                    "Section '%s' generated: %d words",
                    section,
                    len(text.split()),
                )
            except Exception as exc:
                logger.error("Section '%s' failed: %s", section, exc)
                briefing.pipeline_errors.append(f"{section}: {exc}")
                briefing.sections[section] = self._section_fallback(
                    section, section_data.get(section, {})
                )

        # Generate appendix
        self._generate_appendix(
            briefing, market, articles, deals, deal_analysis, interview_content
        )

    # ── Section generation helpers ──────────────────────────────────────

    def _generate_section(
        self, section: str, data: dict, cfg: dict
    ) -> str:
        """Generate one section: render the prompt template, call LLM."""
        prompt = self._render_prompt(section, **data)

        # Scale max_tokens to target word count (rough: 1 word ~ 1.5 tokens)
        estimated_tokens = int(cfg["target_words"] * 1.8)
        max_tokens = min(estimated_tokens, self.llm.max_tokens)

        text = self.llm.generate(prompt, system=SYSTEM_PROMPT, max_tokens=max_tokens)

        if not text:
            logger.warning(
                "LLM returned empty for section '%s', using fallback", section
            )
            text = self._section_fallback(section, data)

        return text

    def _render_prompt(self, section: str, **kwargs) -> str:
        """Render a Jinja2 prompt template for a section."""
        if self.prompt_env:
            try:
                template = self.prompt_env.get_template(f"{section}.md")
                return template.render(**kwargs)
            except Exception as exc:
                logger.warning(
                    "Template '%s.md' failed: %s, using fallback prompt",
                    section,
                    exc,
                )
        return self._fallback_prompt(section, **kwargs)

    def _fallback_prompt(self, section: str, **kwargs) -> str:
        """Generate a basic prompt when the template file is missing."""
        date = kwargs.get("date", datetime.now().strftime("%Y-%m-%d"))
        target_words = kwargs.get("target_words", 300)
        section_label = section.replace("_", " ").title()

        parts = [
            f"Write the '{section_label}' section of a daily financial briefing "
            f"for {date}. Target approximately {target_words} words. "
            f"Output HTML with <p> tags for paragraphs and <a href> links to sources. "
            f"Write in a professional, analytical tone.\n"
        ]

        # Include whatever data we have
        market_data = kwargs.get("market_data")
        if market_data and isinstance(market_data, dict):
            parts.append("\n## Market Data")
            indices = market_data.get("indices", {})
            for name, val in indices.items():
                if val is not None:
                    parts.append(f"- {name}: {val}")

        articles = kwargs.get("articles") or kwargs.get("macro_articles") or []
        if articles:
            parts.append("\n## Headlines")
            for a in articles[:5]:
                if isinstance(a, Article):
                    parts.append(f"- {a.title} ({a.source})")
                elif isinstance(a, dict):
                    parts.append(
                        f"- {a.get('title', 'Untitled')} ({a.get('source', '')})"
                    )

        deal = kwargs.get("deal")
        if deal and isinstance(deal, Deal):
            parts.append(f"\n## Featured Deal: {deal.acquirer} / {deal.target}")
            if deal.ev_mm:
                parts.append(f"Enterprise Value: ${deal.ev_mm:,.0f}M")
            if deal.deal_type:
                parts.append(f"Type: {deal.deal_type}")

        return "\n".join(parts)

    def _section_fallback(self, section: str, data: dict) -> str:
        """Generate a minimal HTML fallback when LLM generation fails entirely."""
        section_label = section.replace("_", " ").title()
        parts = [f"<p><strong>[{section_label}]</strong></p>"]

        if section == "opening_brief":
            articles = data.get("articles", [])
            if articles:
                parts.append("Today's top stories:")
                for a in articles[:3]:
                    if isinstance(a, Article):
                        parts.append(f"  - {a.title}")
                    elif isinstance(a, dict):
                        parts.append(f"  - {a.get('title', '')}")

        elif section == "markets_macro":
            market_data = data.get("market_data", {})
            if isinstance(market_data, dict):
                indices = market_data.get("indices", {})
                for name, val in indices.items():
                    if val is not None:
                        changes = market_data.get("index_changes", {})
                        chg = changes.get(name)
                        chg_str = f" ({chg:+.2f}%)" if chg is not None else ""
                        parts.append(f"  {name}: {val:,.2f}{chg_str}")

        elif section == "deal_of_day":
            deal = data.get("deal")
            if isinstance(deal, Deal):
                parts.append(
                    f"  {deal.acquirer} acquiring {deal.target}"
                )
                if deal.ev_mm:
                    parts.append(f"  Enterprise Value: ${deal.ev_mm:,.0f}M")
                if deal.deal_type:
                    parts.append(f"  Type: {deal.deal_type}")
                if deal.consideration:
                    parts.append(f"  Consideration: {deal.consideration}")

        elif section == "pe_pc":
            pe_articles = data.get("pe_pc_articles", [])
            for a in pe_articles[:3]:
                if isinstance(a, Article):
                    parts.append(f"  - {a.title}")

        elif section == "company_insight":
            company_articles = data.get("company_articles", [])
            for a in company_articles[:2]:
                if isinstance(a, Article):
                    parts.append(f"  - {a.title}")

        elif section == "politics_policy":
            pol_articles = data.get("politics_articles", [])
            for a in pol_articles[:3]:
                if isinstance(a, Article):
                    parts.append(f"  - {a.title}")

        elif section == "interview_practice":
            interview = data.get("interview_content", {})
            if isinstance(interview, dict) and interview.get("sample_answer"):
                parts.append(interview["sample_answer"])

        elif section == "what_to_watch":
            forward = data.get("forward_articles", [])
            for a in forward[:3]:
                if isinstance(a, Article):
                    parts.append(f"  - {a.title}")

        return "\n".join(parts)

    # ── Headline generation ─────────────────────────────────────────────

    def _generate_headline(self, briefing: Briefing) -> str:
        """Extract a short headline from the opening brief for email subject."""
        opening = briefing.sections.get("opening_brief", "")
        if not opening:
            return f"Daily Briefing — {briefing.date}"

        prompt = (
            f"Extract a concise headline (maximum 10 words) from this briefing "
            f"opening that captures the day's main theme. Return ONLY the headline "
            f"text, nothing else.\n\n{opening[:500]}"
        )
        headline = self.llm.generate(prompt, system=SYSTEM_PROMPT, max_tokens=50)

        if headline:
            # Clean up: strip quotes, periods, excessive whitespace
            headline = headline.strip().strip('"\'').strip(".")
            if len(headline) > 80:
                headline = headline[:77] + "..."
            return headline

        # Fallback: use first sentence of the opening
        first_sentence = opening.split(".")[0].strip()
        if len(first_sentence) > 80:
            first_sentence = first_sentence[:77] + "..."
        return first_sentence or f"Daily Briefing — {briefing.date}"

    # ── Appendix generation ─────────────────────────────────────────────

    def _generate_appendix(
        self,
        briefing: Briefing,
        market: MarketSnapshot,
        articles: list[Article],
        deals: list[Deal],
        deal_analysis: dict | None = None,
        interview_content: dict | None = None,
    ):
        """Generate written appendix content (not spoken in audio)."""
        deal_analysis = deal_analysis or {}
        interview_content = interview_content or {}

        # Full market table
        briefing.appendix["full_market_table"] = self._format_market_table(
            market
        )

        # Additional stories beyond what was covered in spoken sections
        covered_ids = set()
        for section_text in briefing.sections.values():
            for article in articles:
                if article.title and article.title[:30] in section_text:
                    covered_ids.add(article.id)

        additional = [a for a in articles if a.id not in covered_ids][:10]
        briefing.appendix["additional_stories"] = [
            {"title": a.title, "source": a.source, "url": a.url, "summary": a.summary, "image_url": a.image_url}
            for a in additional
        ]

        # Source links
        all_sources = []
        for article in articles[:20]:
            if article.url:
                all_sources.append(
                    {"title": article.title, "url": article.url, "source": article.source}
                )
        briefing.appendix["source_links"] = all_sources

        # Glossary term of the day
        featured_deal = self._select_featured_deal(deals)
        briefing.appendix["glossary_term"] = self._generate_glossary_term(
            featured_deal, articles
        )

        # Retrieval questions from interview prep
        if interview_content.get("retrieval_questions"):
            briefing.appendix["retrieval_questions"] = interview_content[
                "retrieval_questions"
            ]
        else:
            briefing.appendix["retrieval_questions"] = []

    def _format_market_table(self, market: MarketSnapshot) -> str:
        """Format a complete market data table for the appendix."""
        lines = ["| Metric | Value | Change |", "|--------|-------|--------|"]

        # Indices
        for name, value in market.indices.items():
            if value is not None:
                change = market.index_changes.get(name)
                change_str = f"{change:+.2f}%" if change is not None else "—"
                lines.append(f"| {name} | {value:,.2f} | {change_str} |")

        # Yields
        for tenor, value in market.yields.items():
            if value is not None:
                bps = market.yield_changes_bps.get(tenor)
                bps_str = f"{bps:+.1f} bps" if bps is not None else "—"
                lines.append(f"| {tenor} Treasury | {value:.3f}% | {bps_str} |")

        # Spreads
        for name, value in market.spreads.items():
            if value is not None:
                lines.append(f"| {name} | {value:.0f} bps | — |")

        # Rates
        for name, value in market.rates.items():
            if value is not None:
                lines.append(f"| {name} | {value:.4f}% | — |")

        # FX
        for pair, value in market.fx.items():
            if value is not None:
                lines.append(f"| {pair} | {value:.4f} | — |")

        # Commodities
        for name, value in market.commodities.items():
            if value is not None:
                lines.append(f"| {name} | ${value:,.2f} | — |")

        # VIX
        if market.vix is not None:
            lines.append(f"| VIX | {market.vix:.2f} | — |")

        # Watchlist
        if market.watchlist:
            lines.append("")
            lines.append(
                "| Watchlist | Price | Change |"
            )
            lines.append("|-----------|-------|--------|")
            for item in market.watchlist:
                price_str = f"${item.price:.2f}" if item.price else "—"
                chg_str = (
                    f"{item.change_pct:+.2f}%"
                    if item.change_pct is not None
                    else "—"
                )
                label = f"{item.ticker}"
                if item.name:
                    label += f" ({item.name})"
                lines.append(f"| {label} | {price_str} | {chg_str} |")

        return "\n".join(lines)

    def _generate_glossary_term(
        self, deal: Deal | None, articles: list[Article]
    ) -> dict:
        """Generate the glossary term of the day using the LLM."""
        data = {
            "deal": deal,
            "articles": articles[:5],
        }
        prompt = self._render_prompt("glossary", **data)
        result = self.llm.generate(prompt, system=SYSTEM_PROMPT, max_tokens=300)

        if result:
            return self._parse_glossary_response(result)

        # Fallback glossary term
        return {
            "term": "Enterprise Value (EV)",
            "definition": (
                "Enterprise Value represents the total value of a company, "
                "calculated as market capitalization plus debt, minus cash. "
                "It is the theoretical takeover price and is used in valuation "
                "multiples like EV/EBITDA and EV/Revenue."
            ),
        }

    @staticmethod
    def _parse_glossary_response(text: str) -> dict:
        """Parse the structured glossary response from the LLM."""
        result = {"term": "", "definition": ""}
        lines = text.strip().split("\n")

        for line in lines:
            stripped = line.strip()
            upper = stripped.upper()
            if upper.startswith("TERM:"):
                result["term"] = stripped.split(":", 1)[1].strip()
            elif upper.startswith("DEFINITION:"):
                result["definition"] = stripped.split(":", 1)[1].strip()
            elif upper.startswith("RELEVANCE:"):
                result["relevance"] = stripped.split(":", 1)[1].strip()
            elif upper.startswith("USAGE:"):
                result["usage"] = stripped.split(":", 1)[1].strip()
            elif result.get("definition") and not any(
                upper.startswith(k)
                for k in ("TERM:", "RELEVANCE:", "USAGE:")
            ):
                # Continuation line for definition
                result["definition"] += " " + stripped

        # Ensure we have at least term and definition
        if not result["term"] or not result["definition"]:
            # Try to extract something useful from the raw text
            result["term"] = result.get("term") or "Financial Term"
            result["definition"] = result.get("definition") or text[:200]

        return result

    # ── Deal selection ──────────────────────────────────────────────────

    @staticmethod
    def _select_featured_deal(deals: list[Deal]) -> Deal | None:
        """Select the best deal to feature in the briefing.

        Priority: announced > pending > rumored, then by source article count,
        then by enterprise value.
        """
        if not deals:
            return None

        status_priority = {
            "announced": 0,
            "pending": 1,
            "rumored": 2,
            "completed": 3,
            "terminated": 4,
        }

        def deal_score(d: Deal) -> tuple:
            status_rank = status_priority.get(d.status, 5)
            article_count = len(d.source_articles)
            ev = d.ev_mm or 0
            return (status_rank, -article_count, -ev)

        sorted_deals = sorted(deals, key=deal_score)
        return sorted_deals[0]

    @staticmethod
    def _select_company_articles(
        articles: list[Article], featured_deal: Deal | None
    ) -> list[Article]:
        """Select articles for the company insight section.

        Prefer articles about specific companies (with tickers) that are
        not about the featured deal.
        """
        deal_tickers = set()
        if featured_deal:
            # Exclude tickers directly associated with the featured deal
            deal_title_words = set(
                (featured_deal.target + " " + featured_deal.acquirer)
                .lower()
                .split()
            )
        else:
            deal_title_words = set()

        candidates = []
        for article in articles:
            # Prefer articles with tickers (company-specific news)
            if not article.tickers:
                continue
            # Exclude articles that seem to be about the featured deal
            title_words = set(article.title.lower().split())
            if deal_title_words and len(title_words & deal_title_words) >= 2:
                continue
            candidates.append(article)

        # If not enough ticker-specific articles, add high-relevance ones
        if len(candidates) < 2:
            for article in articles:
                if article not in candidates and article.relevance_score > 0.5:
                    candidates.append(article)
                if len(candidates) >= 4:
                    break

        # Sort by relevance
        candidates.sort(key=lambda a: -a.relevance_score)
        return candidates[:4]
