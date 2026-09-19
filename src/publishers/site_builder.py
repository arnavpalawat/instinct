"""Site builder — renders daily briefing pages from Jinja2 templates."""
import os
import json
import shutil
import logging
from pathlib import Path
from datetime import datetime
from jinja2 import Environment, FileSystemLoader

from src.models.briefing import Briefing

logger = logging.getLogger(__name__)

# Section key -> human-readable label
SECTION_LABELS = {
    "opening_brief": "Opening Brief",
    "markets_macro": "Markets & Macro",
    "deal_of_day": "Deal of the Day",
    "pe_pc": "PE & PC Developments",
    "company_insight": "Company / Sector Insight",
    "interview_practice": "Interview Practice",
    "what_to_watch": "What to Watch",
}

SECTION_ORDER = list(SECTION_LABELS.keys())


class SiteBuilder:
    """Renders daily briefing pages and manages static assets."""

    def __init__(self, config: dict):
        self.base_url = config.get("base_url", "")
        self.briefings_dir = config.get("briefings_dir", "docs/briefings")
        self.assets_dir = config.get("assets_dir", "docs/assets")
        self.template_dir = config.get("template_dir", "templates")
        self.template_env = Environment(
            loader=FileSystemLoader(self.template_dir),
            autoescape=True,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_page(self, briefing: Briefing) -> str:
        """Render daily briefing page. Returns path to generated HTML file."""
        date_dir = os.path.join(self.briefings_dir, briefing.date)
        os.makedirs(date_dir, exist_ok=True)

        # Determine previous/next briefing dates for navigation
        prev_date, next_date = self._adjacent_dates(briefing.date)

        template = self.template_env.get_template("page.html")
        html = template.render(
            briefing=briefing,
            date_formatted=self._format_date(briefing.date),
            duration_formatted=self._format_duration(briefing.audio_duration_sec),
            has_audio=bool(briefing.audio_path),
            sections=briefing.sections,
            section_labels=SECTION_LABELS,
            section_order=SECTION_ORDER,
            appendix=briefing.appendix,
            market=briefing.market_snapshot,
            deals=briefing.deals,
            headline=briefing.headline,
            base_url=self.base_url,
            prev_date=prev_date,
            next_date=next_date,
            generated_at=briefing.generated_at,
            word_count=briefing.word_count,
            pipeline_errors=briefing.pipeline_errors,
        )

        output_path = os.path.join(date_dir, "index.html")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        logger.info("Wrote briefing page: %s", output_path)

        # Persist briefing data as JSON for the index builder
        data_path = os.path.join(date_dir, "data.json")
        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(briefing.to_dict(), f, indent=2, default=str)
        logger.info("Wrote briefing data: %s", data_path)

        return output_path

    def build_fallback_page(self, briefing: Briefing) -> str:
        """Render template-only fallback when LLM is unavailable."""
        date_dir = os.path.join(self.briefings_dir, briefing.date)
        os.makedirs(date_dir, exist_ok=True)

        prev_date, next_date = self._adjacent_dates(briefing.date)

        template = self.template_env.get_template("fallback.html")
        html = template.render(
            briefing=briefing,
            date_formatted=self._format_date(briefing.date),
            market=briefing.market_snapshot,
            deals=briefing.deals,
            appendix=briefing.appendix,
            base_url=self.base_url,
            prev_date=prev_date,
            next_date=next_date,
            generated_at=briefing.generated_at,
        )

        output_path = os.path.join(date_dir, "index.html")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        logger.info("Wrote fallback page: %s", output_path)

        # Also save JSON
        data_path = os.path.join(date_dir, "data.json")
        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(briefing.to_dict(), f, indent=2, default=str)

        return output_path

    def ensure_assets(self):
        """Copy CSS and JS assets into docs/assets/ if not already present."""
        os.makedirs(self.assets_dir, exist_ok=True)

        src_css = os.path.join(self.template_dir, "..", "docs", "assets", "style.css")
        src_js = os.path.join(self.template_dir, "..", "docs", "assets", "player.js")

        # If source templates don't exist at that path, try the canonical location
        for src, name in [(src_css, "style.css"), (src_js, "player.js")]:
            dest = os.path.join(self.assets_dir, name)
            canonical = os.path.join("docs", "assets", name)
            if not os.path.exists(dest):
                if os.path.exists(canonical):
                    shutil.copy2(canonical, dest)
                    logger.info("Copied asset: %s -> %s", canonical, dest)
                else:
                    logger.warning("Asset not found: %s", canonical)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _format_date(self, date_str: str) -> str:
        """Format '2026-09-19' to 'Fri, Sep 19, 2026'."""
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            return dt.strftime("%a, %b %d, %Y")
        except ValueError:
            return date_str

    def _format_duration(self, seconds: int) -> str:
        """Format seconds to 'MM:SS'."""
        if not seconds or seconds <= 0:
            return "0:00"
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}:{secs:02d}"

    def _adjacent_dates(self, current_date: str) -> tuple[str | None, str | None]:
        """Find the previous and next briefing dates relative to *current_date*.

        Scans the briefings directory for existing date-named subdirectories.
        Returns (prev_date, next_date) — either may be None.
        """
        if not os.path.isdir(self.briefings_dir):
            return None, None

        dates: list[str] = sorted(
            d
            for d in os.listdir(self.briefings_dir)
            if os.path.isdir(os.path.join(self.briefings_dir, d))
            and len(d) == 10
            and d[4] == "-"
        )

        prev_date = None
        next_date = None
        for i, d in enumerate(dates):
            if d == current_date:
                if i > 0:
                    prev_date = dates[i - 1]
                if i < len(dates) - 1:
                    next_date = dates[i + 1]
                break
        else:
            # current_date not yet written — find where it would slot in
            before = [d for d in dates if d < current_date]
            after = [d for d in dates if d > current_date]
            if before:
                prev_date = before[-1]
            if after:
                next_date = after[0]

        return prev_date, next_date
