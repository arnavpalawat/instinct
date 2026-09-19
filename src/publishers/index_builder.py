"""Index builder — builds and maintains the archive landing page."""
import os
import json
import logging
from datetime import datetime
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)


class IndexBuilder:
    """Scans the briefings directory and rebuilds the archive index page."""

    def __init__(self, config: dict):
        self.briefings_dir = config.get("briefings_dir", "docs/briefings")
        self.docs_dir = config.get("docs_dir", "docs")
        self.base_url = config.get("base_url", "")
        self.template_dir = config.get("template_dir", "templates")
        self.template_env = Environment(
            loader=FileSystemLoader(self.template_dir),
            autoescape=True,
        )

    def rebuild(self) -> str:
        """Scan briefings directory, rebuild index.html with all editions.

        Returns path to generated index.html.
        """
        editions = self._collect_editions()
        editions.sort(key=lambda e: e["date"], reverse=True)

        template = self.template_env.get_template("index.html")
        html = template.render(
            editions=editions,
            total=len(editions),
            base_url=self.base_url,
            generated_at=datetime.now(),
        )

        output_path = os.path.join(self.docs_dir, "index.html")
        os.makedirs(self.docs_dir, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

        logger.info("Rebuilt index with %d editions: %s", len(editions), output_path)
        return output_path

    # ------------------------------------------------------------------

    def _collect_editions(self) -> list[dict]:
        """Walk briefings directory and load metadata from each data.json."""
        editions: list[dict] = []

        if not os.path.isdir(self.briefings_dir):
            logger.warning("Briefings directory not found: %s", self.briefings_dir)
            return editions

        for name in sorted(os.listdir(self.briefings_dir)):
            entry_path = os.path.join(self.briefings_dir, name)
            # Only consider YYYY-MM-DD directories
            if not os.path.isdir(entry_path) or len(name) != 10 or name[4] != "-":
                continue

            data_file = os.path.join(entry_path, "data.json")
            if not os.path.isfile(data_file):
                continue

            try:
                with open(data_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Skipping %s: %s", data_file, exc)
                continue

            editions.append({
                "date": data.get("date", name),
                "date_formatted": self._format_date(data.get("date", name)),
                "headline": data.get("headline", ""),
                "word_count": data.get("word_count", 0),
                "audio_duration_sec": data.get("audio_duration_sec", 0),
                "duration_formatted": self._format_duration(
                    data.get("audio_duration_sec", 0)
                ),
                "url": f"briefings/{name}/index.html",
                "has_audio": bool(data.get("audio_path")),
            })

        return editions

    @staticmethod
    def _format_date(date_str: str) -> str:
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            return dt.strftime("%a, %b %d, %Y")
        except ValueError:
            return date_str

    @staticmethod
    def _format_duration(seconds: int) -> str:
        if not seconds or seconds <= 0:
            return ""
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}:{secs:02d}"
