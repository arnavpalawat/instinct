"""
Instinct Pipeline Orchestrator
Coordinates: collect → process → generate → publish
"""
import os
import sys
import json
import logging
import yaml
from datetime import datetime, date
from pathlib import Path

from src.collectors.market_data import MarketDataCollector
from src.collectors.news import NewsCollector
from src.collectors.deals import DealCollector
from src.collectors.filings import FilingsCollector
from src.processors.content_fetcher import ContentFetcher
from src.processors.deduplicator import Deduplicator
from src.processors.ranker import Ranker
from src.processors.extractor import Extractor
from src.processors.verifier import Verifier
from src.generators.llm_client import LLMClient
from src.generators.briefing import BriefingGenerator
from src.generators.deal_analyzer import DealAnalyzer
from src.generators.interview_prep import InterviewPrepGenerator
from src.publishers.site_builder import SiteBuilder
from src.publishers.index_builder import IndexBuilder
from src.publishers.email_sender import EmailSender
from src.models.briefing import Briefing

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("instinct")


def load_config() -> dict:
    """Load all configuration files."""
    config = {}
    config_dir = Path("config")

    for name in ["settings", "watchlist", "sectors"]:
        path = config_dir / f"{name}.yaml"
        if path.exists():
            with open(path) as f:
                config[name] = yaml.safe_load(f) or {}
        else:
            config[name] = {}
            logger.warning(f"Config file not found: {path}")

    return config



def run(dry_run: bool = False):
    """Execute the full pipeline."""
    start_time = datetime.now()
    logger.info("=" * 60)
    logger.info("INSTINCT PIPELINE — %s", date.today().isoformat())
    logger.info("=" * 60)

    config = load_config()
    settings = config["settings"]
    errors: list[str] = []

    # ── STAGE 1: COLLECT ─────────────────────────────────────────
    logger.info("STAGE 1: Collecting data...")

    market = _collect_market_data(config, errors)
    articles = _collect_articles(config, errors)

    logger.info(
        "Collected: market=%s, articles=%d",
        "OK" if market else "PARTIAL",
        len(articles),
    )

    # ── STAGE 1.5: FETCH CONTENT ─────────────────────────────────
    try:
        fetcher = ContentFetcher(settings)
        fetcher.fetch_all(articles)
    except Exception as e:
        logger.error("Content fetching failed: %s", e)
        errors.append(f"Content fetch: {e}")

    # ── STAGE 2: PROCESS ─────────────────────────────────────────
    logger.info("STAGE 2: Processing articles...")

    articles = _process_articles(articles, config, errors)
    deals = _extract_deals(articles, config, errors)

    logger.info("Processed: articles=%d, deals=%d", len(articles), len(deals))

    # ── STAGE 3: GENERATE ────────────────────────────────────────
    logger.info("STAGE 3: Generating briefing...")

    briefing = _generate_briefing(market, articles, deals, config, errors)
    briefing.pipeline_errors = errors

    logger.info(
        "Generated: %d words, %d sections",
        briefing.word_count,
        sum(1 for v in briefing.sections.values() if v),
    )

    # ── STAGE 4: PUBLISH ─────────────────────────────────────────
    logger.info("STAGE 4: Publishing...")

    if dry_run:
        _print_briefing(briefing)
        logger.info("DRY RUN — skipping publish and email")
    else:
        page_path = _publish(briefing, config, errors)
        _send_email(briefing, page_path, config, errors)

    # ── DONE ─────────────────────────────────────────────────────
    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE in %.1fs", elapsed)
    if errors:
        logger.warning("Errors encountered (%d):", len(errors))
        for err in errors:
            logger.warning("  - %s", err)
    logger.info("=" * 60)

    return briefing


def _collect_market_data(config, errors):
    """Collect market data with fallbacks."""
    try:
        collector = MarketDataCollector(config["settings"])
        snapshot = collector.collect()

        # Verify data quality
        verifier = Verifier()
        snapshot = verifier.verify_market_data(snapshot)
        return snapshot
    except Exception as e:
        logger.error("Market data collection failed: %s", e)
        errors.append(f"Market data: {e}")
        from src.models.market_snapshot import MarketSnapshot
        return MarketSnapshot()


def _collect_articles(config, errors):
    """Collect articles from all sources."""
    articles = []

    # News
    try:
        news_collector = NewsCollector(config["settings"])
        news = news_collector.collect(
            sectors=list(config["sectors"].keys()),
        )
        articles.extend(news)
        logger.info("News: %d articles", len(news))
    except Exception as e:
        logger.error("News collection failed: %s", e)
        errors.append(f"News: {e}")

    # Deal press releases
    try:
        deal_collector = DealCollector(config["settings"])
        deal_articles = deal_collector.collect()
        articles.extend(deal_articles)
        logger.info("Deals: %d articles", len(deal_articles))
    except Exception as e:
        logger.error("Deal collection failed: %s", e)
        errors.append(f"Deals: {e}")

    # SEC filings
    try:
        filings_collector = FilingsCollector(config["settings"])
        filings = filings_collector.collect()
        articles.extend(filings)
        logger.info("Filings: %d articles", len(filings))
    except Exception as e:
        logger.error("Filings collection failed: %s", e)
        errors.append(f"Filings: {e}")

    return articles


def _process_articles(articles, config, errors):
    """Deduplicate, classify, and rank articles."""
    try:
        # Classify sectors and extract tickers
        extractor = Extractor()
        articles = extractor.classify_sectors(articles, config["sectors"])
        articles = extractor.extract_tickers(articles)

        # Deduplicate
        dedup = Deduplicator()
        articles = dedup.deduplicate(articles)

        # Rank
        ranker = Ranker()
        articles = ranker.rank(articles)

        # Verify
        verifier = Verifier()
        articles = verifier.verify_articles(articles)

        return articles
    except Exception as e:
        logger.error("Processing failed: %s", e)
        errors.append(f"Processing: {e}")
        return articles


def _extract_deals(articles, config, errors):
    """Extract structured deal data from articles."""
    try:
        extractor = Extractor()
        deal_articles = [a for a in articles if a.is_deal_related]
        deals = extractor.extract_deals(deal_articles)

        # Verify deals
        verifier = Verifier()
        deals = [verifier.verify_deal(d) for d in deals]

        return deals
    except Exception as e:
        logger.error("Deal extraction failed: %s", e)
        errors.append(f"Deal extraction: {e}")
        return []


def _generate_briefing(market, articles, deals, config, errors):
    """Generate briefing content via LLM."""
    try:
        llm = LLMClient(config["settings"].get("llm", {}))
        generator = BriefingGenerator(llm, config["settings"])
        briefing = generator.generate(
            market=market,
            articles=articles,
            deals=deals,
        )

        # Store top articles for the template (prioritize those with images)
        with_images = [a for a in articles if a.image_url]
        without_images = [a for a in articles if not a.image_url]
        top_pool = with_images[:8]
        if len(top_pool) < 8:
            top_pool.extend(without_images[: 8 - len(top_pool)])
        briefing.top_articles = [a.to_dict() for a in top_pool[:8]]

        # Generate deal analysis for top deal
        if deals:
            try:
                analyzer = DealAnalyzer(llm)
                deal_analysis = analyzer.analyze(deals[0], articles)
                briefing.sections["deal_of_day"] = deal_analysis.get(
                    "full_section", briefing.sections.get("deal_of_day", "")
                )
            except Exception as e:
                logger.error("Deal analysis failed: %s", e)
                errors.append(f"Deal analysis: {e}")

            # Generate interview prep
            try:
                interview = InterviewPrepGenerator(llm)
                prep = interview.generate(deals[0], {}, market, articles)
                if prep.get("full_section"):
                    briefing.sections["interview_practice"] = prep["full_section"]
            except Exception as e:
                logger.error("Interview prep failed: %s", e)
                errors.append(f"Interview prep: {e}")

        return briefing
    except Exception as e:
        logger.error("Briefing generation failed: %s", e)
        errors.append(f"Briefing generation: {e}")
        return Briefing()


def _publish(briefing, config, errors):
    """Publish HTML pages."""
    try:
        pub_config = config["settings"].get("publishing", {})
        builder = SiteBuilder(pub_config)
        builder.ensure_assets()
        page_path = builder.build_page(briefing)

        # Rebuild index
        index_builder = IndexBuilder(pub_config)
        index_builder.rebuild()

        logger.info("Published: %s", page_path)
        return page_path
    except Exception as e:
        logger.error("Publishing failed: %s", e)
        errors.append(f"Publishing: {e}")
        return ""


def _send_email(briefing, page_path, config, errors):
    """Send email notification."""
    try:
        email_config = config["settings"].get("email", {})
        sender = EmailSender(email_config)

        recipient = os.environ.get(
            "RECIPIENT_EMAIL",
            config["settings"].get("user", {}).get("email", ""),
        )
        if not recipient:
            logger.warning("No recipient email configured — skipping email")
            return

        base_url = config["settings"].get("publishing", {}).get("base_url", "")
        page_url = f"{base_url}/briefings/{briefing.date}/" if base_url else ""

        success = sender.send(briefing, recipient, page_url)
        if success:
            logger.info("Email sent to %s", recipient)
        else:
            errors.append("Email sending failed")
    except Exception as e:
        logger.error("Email failed: %s", e)
        errors.append(f"Email: {e}")


def _print_briefing(briefing):
    """Print briefing to stdout for dry run."""
    print("\n" + "=" * 60)
    print(f"INSTINCT — {briefing.date}")
    print("=" * 60)

    section_titles = {
        "opening_brief": "OPENING BRIEF",
        "markets_macro": "MARKETS & MACRO",
        "deal_of_day": "DEAL OF THE DAY",
        "pe_pc": "PE & PC DEVELOPMENTS",
        "company_insight": "COMPANY/SECTOR INSIGHT",
        "politics_policy": "POLITICS & POLICY",
        "interview_practice": "INTERVIEW PRACTICE",
        "what_to_watch": "WHAT TO WATCH",
    }

    for key, title in section_titles.items():
        content = briefing.sections.get(key, "")
        if content:
            print(f"\n{'─' * 40}")
            print(f"§ {title}")
            print(f"{'─' * 40}")
            print(content)

    if briefing.pipeline_errors:
        print(f"\n{'─' * 40}")
        print("PIPELINE ERRORS:")
        for err in briefing.pipeline_errors:
            print(f"  ⚠ {err}")

    print(f"\n{'=' * 60}")
    print(f"Words: {briefing.word_count}")
    print("=" * 60)


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv or "-d" in sys.argv
    run(dry_run=dry_run)
