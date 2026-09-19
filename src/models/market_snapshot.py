"""Market snapshot data model."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class WatchlistItem:
    ticker: str
    price: Optional[float] = None
    change_pct: Optional[float] = None
    prev_close: Optional[float] = None
    name: str = ""
    sector: str = ""

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "price": self.price,
            "chg_pct": self.change_pct,
            "prev_close": self.prev_close,
            "name": self.name,
            "sector": self.sector,
        }


@dataclass
class MarketSnapshot:
    timestamp: datetime = field(default_factory=datetime.now)
    observation_type: str = "prior_close"  # "prior_close" | "premarket" | "live"

    # Indices
    indices: dict[str, Optional[float]] = field(default_factory=lambda: {
        "SP500": None, "NASDAQ": None, "DJIA": None, "Russell2000": None,
    })
    index_changes: dict[str, Optional[float]] = field(default_factory=dict)

    # Fixed income
    yields: dict[str, Optional[float]] = field(default_factory=lambda: {
        "2Y": None, "10Y": None, "30Y": None,
    })
    yield_changes_bps: dict[str, Optional[float]] = field(default_factory=dict)

    # Credit
    spreads: dict[str, Optional[float]] = field(default_factory=lambda: {
        "IG_OAS": None, "HY_OAS": None,
    })

    # Rates
    rates: dict[str, Optional[float]] = field(default_factory=lambda: {
        "SOFR": None, "FedFunds": None,
    })

    # FX & Commodities
    fx: dict[str, Optional[float]] = field(default_factory=lambda: {
        "DXY": None, "EURUSD": None,
    })
    commodities: dict[str, Optional[float]] = field(default_factory=lambda: {
        "WTI": None, "Gold": None,
    })

    vix: Optional[float] = None

    # Watchlist
    watchlist: list[WatchlistItem] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "observation_type": self.observation_type,
            "indices": self.indices,
            "index_changes": self.index_changes,
            "yields": self.yields,
            "yield_changes_bps": self.yield_changes_bps,
            "spreads": self.spreads,
            "rates": self.rates,
            "fx": self.fx,
            "commodities": self.commodities,
            "vix": self.vix,
            "watchlist": [w.to_dict() for w in self.watchlist],
        }

    def is_stale(self, max_age_hours: float = 20) -> bool:
        age = (datetime.now() - self.timestamp).total_seconds() / 3600
        return age > max_age_hours
