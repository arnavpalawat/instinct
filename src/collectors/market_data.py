"""Market data collector using Finnhub, yfinance, and FRED APIs."""
import logging
import os
import time
from datetime import datetime
from typing import Optional

import finnhub
import yfinance as yf
from fredapi import Fred

from src.models.market_snapshot import MarketSnapshot, WatchlistItem

logger = logging.getLogger(__name__)


class MarketDataCollector:
    """Collects market data from multiple free API sources with fallbacks."""

    # Index mappings: friendly name -> (yfinance symbol, finnhub symbol)
    INDEX_MAP = {
        "SP500": ("^GSPC", "SPY"),
        "NASDAQ": ("^IXIC", "QQQ"),
        "DJIA": ("^DJI", "DIA"),
        "Russell2000": ("^RUT", "IWM"),
    }

    YIELD_FRED_SERIES = {
        "2Y": "DGS2",
        "10Y": "DGS10",
        "30Y": "DGS30",
    }

    YIELD_YF_FALLBACK = {
        "10Y": "^TNX",
        "30Y": "^TYX",
    }

    SPREAD_SERIES = {
        "IG_OAS": "BAMLC0A0CM",
        "HY_OAS": "BAMLH0A0HYM2",
    }

    RATE_SERIES = {
        "SOFR": "SOFR",
        "FedFunds": "FEDFUNDS",
    }

    FX_COMMODITY_SYMBOLS = {
        "DXY": "DX-Y.NYB",
        "EURUSD": "EURUSD=X",
        "WTI": "CL=F",
        "Gold": "GC=F",
    }

    def __init__(self, config: dict):
        self.config = config
        self.finnhub_key = os.environ.get("FINNHUB_API_KEY", "")
        self.fred_key = os.environ.get("FRED_API_KEY", "")
        self.fmp_key = os.environ.get("FMP_API_KEY", "")

        self.finnhub_client: Optional[finnhub.Client] = None
        if self.finnhub_key:
            try:
                self.finnhub_client = finnhub.Client(api_key=self.finnhub_key)
            except Exception as exc:
                logger.warning("Failed to initialise Finnhub client: %s", exc)

        self.fred_client: Optional[Fred] = None
        if self.fred_key:
            try:
                self.fred_client = Fred(api_key=self.fred_key)
            except Exception as exc:
                logger.warning("Failed to initialise FRED client: %s", exc)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def collect(self) -> MarketSnapshot:
        """Orchestrate all data collection, returning a MarketSnapshot.

        Each sub-collector is wrapped in its own try/except so that a failure
        in one area does not prevent the rest of the snapshot from populating.
        """
        snapshot = MarketSnapshot(timestamp=datetime.now())

        # Indices
        indices_data = self._fetch_indices()
        if indices_data:
            for key in snapshot.indices:
                if key in indices_data:
                    snapshot.indices[key] = indices_data[key].get("price")
                    if indices_data[key].get("change_pct") is not None:
                        snapshot.index_changes[key] = indices_data[key]["change_pct"]

        # Yields
        yields_data = self._fetch_yields()
        if yields_data:
            for key in snapshot.yields:
                if key in yields_data:
                    snapshot.yields[key] = yields_data[key]

        # Spreads
        spreads_data = self._fetch_spreads()
        if spreads_data:
            for key in snapshot.spreads:
                if key in spreads_data:
                    snapshot.spreads[key] = spreads_data[key]

        # Rates
        rates_data = self._fetch_rates()
        if rates_data:
            for key in snapshot.rates:
                if key in rates_data:
                    snapshot.rates[key] = rates_data[key]

        # FX & Commodities
        fx_comm = self._fetch_fx_commodities()
        if fx_comm:
            for key in snapshot.fx:
                if key in fx_comm:
                    snapshot.fx[key] = fx_comm[key]
            for key in snapshot.commodities:
                if key in fx_comm:
                    snapshot.commodities[key] = fx_comm[key]

        # VIX
        vix_val = self._fetch_vix()
        if vix_val is not None:
            snapshot.vix = vix_val

        # Watchlist
        watchlist_tickers = self.config.get("watchlist", [])
        if watchlist_tickers:
            snapshot.watchlist = self._fetch_watchlist(watchlist_tickers)

        logger.info("Market snapshot collected at %s", snapshot.timestamp.isoformat())
        return snapshot

    # ------------------------------------------------------------------
    # Index data
    # ------------------------------------------------------------------

    def _fetch_indices(self) -> Optional[dict]:
        """Fetch major index prices and daily change percentages.

        Primary source: yfinance. Fallback: Finnhub (using ETF proxies).
        Returns a dict keyed by index name with sub-keys 'price' and 'change_pct'.
        """
        result: dict = {}

        # --- Primary: yfinance ---
        try:
            for name, (yf_symbol, _) in self.INDEX_MAP.items():
                try:
                    ticker = yf.Ticker(yf_symbol)
                    info = ticker.info
                    price = info.get("regularMarketPrice") or info.get("previousClose")
                    prev_close = info.get("previousClose")
                    change_pct = None
                    if price and prev_close and prev_close != 0:
                        change_pct = round((price - prev_close) / prev_close * 100, 2)
                    result[name] = {"price": price, "change_pct": change_pct}
                except Exception as exc:
                    logger.debug("yfinance failed for index %s: %s", name, exc)
            if result:
                return result
        except Exception as exc:
            logger.warning("yfinance index fetch failed globally: %s", exc)

        # --- Fallback: Finnhub (ETF proxies) ---
        if not self.finnhub_client:
            logger.warning("No Finnhub client available for index fallback")
            return None

        try:
            for name, (_, fh_symbol) in self.INDEX_MAP.items():
                try:
                    quote = self.finnhub_client.quote(fh_symbol)
                    price = quote.get("c")  # current price
                    prev_close = quote.get("pc")  # previous close
                    change_pct = None
                    if price and prev_close and prev_close != 0:
                        change_pct = round((price - prev_close) / prev_close * 100, 2)
                    result[name] = {"price": price, "change_pct": change_pct}
                    time.sleep(0.15)  # rate limit courtesy
                except Exception as exc:
                    logger.debug("Finnhub failed for index proxy %s: %s", fh_symbol, exc)
        except Exception as exc:
            logger.error("Finnhub index fallback failed: %s", exc)

        return result if result else None

    # ------------------------------------------------------------------
    # Yield data
    # ------------------------------------------------------------------

    def _fetch_yields(self) -> Optional[dict]:
        """Fetch treasury yields from FRED; fall back to yfinance for 10Y/30Y."""
        result: dict = {}

        # --- Primary: FRED ---
        if self.fred_client:
            for name, series_id in self.YIELD_FRED_SERIES.items():
                try:
                    series = self.fred_client.get_series_latest_release(series_id)
                    latest = series.dropna().iloc[-1] if not series.dropna().empty else None
                    if latest is not None:
                        result[name] = round(float(latest), 3)
                except Exception as exc:
                    logger.debug("FRED yield fetch failed for %s: %s", series_id, exc)

        # --- Fallback: yfinance for missing tenors ---
        missing = [k for k in self.YIELD_FRED_SERIES if k not in result]
        if missing:
            for name in missing:
                yf_sym = self.YIELD_YF_FALLBACK.get(name)
                if not yf_sym:
                    continue
                try:
                    ticker = yf.Ticker(yf_sym)
                    info = ticker.info
                    price = info.get("regularMarketPrice")
                    if price is not None:
                        # ^TNX and ^TYX quote in basis-like terms (e.g. 4.25 for 4.25%)
                        result[name] = round(float(price), 3)
                except Exception as exc:
                    logger.debug("yfinance yield fallback failed for %s: %s", name, exc)

        return result if result else None

    # ------------------------------------------------------------------
    # Credit spreads
    # ------------------------------------------------------------------

    def _fetch_spreads(self) -> Optional[dict]:
        """Fetch IG and HY OAS from FRED."""
        if not self.fred_client:
            logger.warning("No FRED client available for spread data")
            return None

        result: dict = {}
        for name, series_id in self.SPREAD_SERIES.items():
            try:
                series = self.fred_client.get_series_latest_release(series_id)
                latest = series.dropna().iloc[-1] if not series.dropna().empty else None
                if latest is not None:
                    result[name] = round(float(latest), 2)
            except Exception as exc:
                logger.debug("FRED spread fetch failed for %s: %s", series_id, exc)

        return result if result else None

    # ------------------------------------------------------------------
    # Short-term rates
    # ------------------------------------------------------------------

    def _fetch_rates(self) -> Optional[dict]:
        """Fetch SOFR and Fed Funds rate from FRED."""
        if not self.fred_client:
            logger.warning("No FRED client available for rate data")
            return None

        result: dict = {}
        for name, series_id in self.RATE_SERIES.items():
            try:
                series = self.fred_client.get_series_latest_release(series_id)
                latest = series.dropna().iloc[-1] if not series.dropna().empty else None
                if latest is not None:
                    result[name] = round(float(latest), 4)
            except Exception as exc:
                logger.debug("FRED rate fetch failed for %s: %s", series_id, exc)

        return result if result else None

    # ------------------------------------------------------------------
    # FX & Commodities
    # ------------------------------------------------------------------

    def _fetch_fx_commodities(self) -> Optional[dict]:
        """Fetch DXY, EUR/USD, WTI crude, and Gold via yfinance."""
        result: dict = {}
        for name, symbol in self.FX_COMMODITY_SYMBOLS.items():
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.info
                price = info.get("regularMarketPrice") or info.get("previousClose")
                if price is not None:
                    result[name] = round(float(price), 4)
            except Exception as exc:
                logger.debug("yfinance FX/commodity fetch failed for %s: %s", symbol, exc)

        return result if result else None

    # ------------------------------------------------------------------
    # VIX
    # ------------------------------------------------------------------

    def _fetch_vix(self) -> Optional[float]:
        """Fetch the CBOE VIX index via yfinance."""
        try:
            ticker = yf.Ticker("^VIX")
            info = ticker.info
            price = info.get("regularMarketPrice") or info.get("previousClose")
            if price is not None:
                return round(float(price), 2)
        except Exception as exc:
            logger.warning("VIX fetch failed: %s", exc)
        return None

    # ------------------------------------------------------------------
    # Watchlist
    # ------------------------------------------------------------------

    def _fetch_watchlist(self, tickers: list) -> list[WatchlistItem]:
        """Batch-fetch watchlist prices via yfinance.download for efficiency."""
        items: list[WatchlistItem] = []

        if not tickers:
            return items

        # First try batch download for prices
        prices: dict = {}
        try:
            df = yf.download(tickers, period="2d", progress=False, group_by="ticker")
            for t in tickers:
                try:
                    if len(tickers) == 1:
                        col = df
                    else:
                        col = df[t]
                    closes = col["Close"].dropna()
                    if len(closes) >= 1:
                        prices[t] = {
                            "price": round(float(closes.iloc[-1]), 2),
                            "prev_close": round(float(closes.iloc[-2]), 2) if len(closes) >= 2 else None,
                        }
                except Exception:
                    pass
        except Exception as exc:
            logger.warning("yfinance batch download failed: %s", exc)

        # Build WatchlistItem objects, enriching with ticker info
        for t in tickers:
            price_info = prices.get(t, {})
            price = price_info.get("price")
            prev_close = price_info.get("prev_close")
            change_pct = None
            if price is not None and prev_close is not None and prev_close != 0:
                change_pct = round((price - prev_close) / prev_close * 100, 2)

            name = ""
            sector = ""
            try:
                info = yf.Ticker(t).info
                name = info.get("shortName", "") or info.get("longName", "")
                sector = info.get("sector", "")
                # Fill price from info if batch download missed it
                if price is None:
                    price = info.get("regularMarketPrice") or info.get("previousClose")
                    if price is not None:
                        price = round(float(price), 2)
                if prev_close is None:
                    prev_close_val = info.get("previousClose")
                    if prev_close_val is not None:
                        prev_close = round(float(prev_close_val), 2)
                    if price is not None and prev_close is not None and prev_close != 0:
                        change_pct = round((price - prev_close) / prev_close * 100, 2)
            except Exception as exc:
                logger.debug("yfinance info fetch failed for %s: %s", t, exc)

            items.append(WatchlistItem(
                ticker=t,
                price=price,
                change_pct=change_pct,
                prev_close=prev_close,
                name=name,
                sector=sector,
            ))

        return items
