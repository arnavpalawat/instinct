"""Article data model for collected news items."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import hashlib


@dataclass
class Article:
    title: str
    url: str
    source: str  # "finnhub" | "google_news" | "pr_newswire" | "businesswire" | "sec_edgar"
    published: Optional[datetime] = None
    summary: str = ""
    tickers: list[str] = field(default_factory=list)
    sectors: list[str] = field(default_factory=list)
    relevance_score: float = 0.0
    is_deal_related: bool = False
    raw_content: str = ""
    id: str = ""

    def __post_init__(self):
        if not self.id:
            hash_input = f"{self.title}:{self.url}:{self.source}"
            self.id = hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "published": self.published.isoformat() if self.published else None,
            "summary": self.summary,
            "tickers": self.tickers,
            "sectors": self.sectors,
            "relevance_score": self.relevance_score,
            "is_deal_related": self.is_deal_related,
        }
