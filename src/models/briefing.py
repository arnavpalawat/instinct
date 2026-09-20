"""Briefing data model — the complete daily output."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Briefing:
    date: str = ""  # YYYY-MM-DD
    generated_at: Optional[datetime] = None
    info_cutoff: Optional[datetime] = None
    is_weekend: bool = False

    # Main sections (spoken)
    sections: dict[str, str] = field(default_factory=lambda: {
        "opening_brief": "",
        "markets_macro": "",
        "deal_of_day": "",
        "pe_pc": "",
        "company_insight": "",
        "interview_practice": "",
        "what_to_watch": "",
    })

    # Written appendix (not spoken)
    appendix: dict = field(default_factory=lambda: {
        "full_market_table": "",
        "additional_stories": [],
        "source_links": [],
        "glossary_term": {"term": "", "definition": ""},
        "retrieval_questions": [],
    })

    # Audio
    audio_path: str = ""
    audio_duration_sec: int = 0

    # Metadata
    word_count: int = 0
    headline: str = ""
    deals: list = field(default_factory=list)
    market_snapshot: dict = field(default_factory=dict)
    top_articles: list = field(default_factory=list)
    pipeline_errors: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.date:
            self.date = datetime.now().strftime("%Y-%m-%d")
        if not self.generated_at:
            self.generated_at = datetime.now()

    def spoken_text(self) -> str:
        """Concatenate all spoken sections for TTS."""
        order = [
            "opening_brief", "markets_macro", "deal_of_day",
            "pe_pc", "company_insight", "interview_practice", "what_to_watch",
        ]
        parts = []
        for key in order:
            text = self.sections.get(key, "")
            if text:
                parts.append(text)
        return "\n\n".join(parts)

    def compute_word_count(self):
        self.word_count = len(self.spoken_text().split())

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
            "info_cutoff": self.info_cutoff.isoformat() if self.info_cutoff else None,
            "is_weekend": self.is_weekend,
            "sections": self.sections,
            "appendix": self.appendix,
            "audio_path": self.audio_path,
            "audio_duration_sec": self.audio_duration_sec,
            "word_count": self.word_count,
            "headline": self.headline,
            "pipeline_errors": self.pipeline_errors,
        }
