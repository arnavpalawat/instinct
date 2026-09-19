"""Deal data model for M&A / PE / PC transactions."""
from dataclasses import dataclass, field
from datetime import date
from typing import Optional
import hashlib


@dataclass
class Deal:
    target: str
    acquirer: str
    deal_type: str = ""  # "Strategic M&A" | "LBO" | "Take-Private" | "Merger" | "Carve-out"
    ev_mm: Optional[float] = None  # Enterprise value in millions
    equity_value_mm: Optional[float] = None
    ev_revenue: Optional[str] = None  # e.g., "15x"
    ev_ebitda: Optional[str] = None
    premium_pct: Optional[float] = None
    consideration: str = ""  # "all-cash" | "all-stock" | "cash-and-stock"
    financing: str = ""  # Description of financing structure
    status: str = "rumored"  # "rumored" | "announced" | "pending" | "completed" | "terminated"
    announced_date: Optional[date] = None
    expected_close: str = ""
    sector: str = ""
    advisors: dict[str, list[str]] = field(default_factory=lambda: {"target": [], "acquirer": []})
    source_articles: list[str] = field(default_factory=list)
    first_covered: Optional[date] = None
    last_updated: Optional[date] = None
    seller: str = ""  # For PE exits / carve-outs
    sponsor: str = ""  # PE sponsor involved
    target_description: str = ""
    geography: str = ""
    id: str = ""

    def __post_init__(self):
        if not self.id:
            hash_input = f"{self.target}:{self.acquirer}:{self.deal_type}"
            self.id = hashlib.sha256(hash_input.encode()).hexdigest()[:16]
        if not self.first_covered:
            self.first_covered = date.today()
        if not self.last_updated:
            self.last_updated = date.today()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "target": self.target,
            "acquirer": self.acquirer,
            "deal_type": self.deal_type,
            "ev_mm": self.ev_mm,
            "equity_value_mm": self.equity_value_mm,
            "ev_revenue": self.ev_revenue,
            "ev_ebitda": self.ev_ebitda,
            "premium_pct": self.premium_pct,
            "consideration": self.consideration,
            "financing": self.financing,
            "status": self.status,
            "announced_date": self.announced_date.isoformat() if self.announced_date else None,
            "expected_close": self.expected_close,
            "sector": self.sector,
            "advisors": self.advisors,
            "source_articles": self.source_articles,
            "first_covered": self.first_covered.isoformat() if self.first_covered else None,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
            "seller": self.seller,
            "sponsor": self.sponsor,
            "target_description": self.target_description,
            "geography": self.geography,
        }
