#!/usr/bin/env python3
"""CLI helper for editing the Instinct watchlist."""
import sys
import yaml
from pathlib import Path

WATCHLIST_PATH = Path("config/watchlist.yaml")


def load():
    with open(WATCHLIST_PATH) as f:
        return yaml.safe_load(f)


def save(data):
    with open(WATCHLIST_PATH, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def add_ticker(symbol: str, sector: str = "", priority: str = "medium"):
    data = load()
    for t in data.get("tickers", []):
        if t["symbol"] == symbol.upper():
            print(f"{symbol.upper()} already in watchlist")
            return
    data.setdefault("tickers", []).append({
        "symbol": symbol.upper(),
        "sector": sector or "General",
        "priority": priority,
    })
    save(data)
    print(f"Added {symbol.upper()} ({sector or 'General'}, {priority})")


def remove_ticker(symbol: str):
    data = load()
    original = len(data.get("tickers", []))
    data["tickers"] = [t for t in data.get("tickers", []) if t["symbol"] != symbol.upper()]
    if len(data["tickers"]) < original:
        save(data)
        print(f"Removed {symbol.upper()}")
    else:
        print(f"{symbol.upper()} not found in watchlist")


def add_firm(name: str, firm_type: str = "bank"):
    data = load()
    for f in data.get("firms", []):
        if f["name"].lower() == name.lower():
            print(f"{name} already in watchlist")
            return
    data.setdefault("firms", []).append({"name": name, "type": firm_type})
    save(data)
    print(f"Added firm: {name} ({firm_type})")


def add_deal(target: str, acquirer: str, sector: str = "", status: str = "announced"):
    data = load()
    data.setdefault("active_deals", []).append({
        "target": target,
        "acquirer": acquirer,
        "sector": sector,
        "status": status,
        "announced": str(__import__("datetime").date.today()),
    })
    save(data)
    print(f"Added deal: {acquirer} → {target}")


def list_watchlist():
    data = load()
    print(f"\nTickers ({len(data.get('tickers', []))}):")
    for t in data.get("tickers", []):
        print(f"  {t['symbol']:8s} {t.get('sector', ''):12s} {t.get('priority', '')}")
    print(f"\nFirms ({len(data.get('firms', []))}):")
    for f in data.get("firms", []):
        print(f"  {f['name']:30s} {f.get('type', '')}")
    print(f"\nActive Deals ({len(data.get('active_deals', []))}):")
    for d in data.get("active_deals", []):
        print(f"  {d.get('acquirer', '?')} → {d.get('target', '?')} [{d.get('status', '')}]")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python scripts/update_watchlist.py list")
        print("  python scripts/update_watchlist.py add-ticker AAPL TMT high")
        print("  python scripts/update_watchlist.py remove-ticker AAPL")
        print("  python scripts/update_watchlist.py add-firm 'Goldman Sachs' bank")
        print("  python scripts/update_watchlist.py add-deal 'Target Co' 'Buyer Co' TMT")
        return

    cmd = sys.argv[1]
    if cmd == "list":
        list_watchlist()
    elif cmd == "add-ticker" and len(sys.argv) >= 3:
        add_ticker(sys.argv[2], *sys.argv[3:5])
    elif cmd == "remove-ticker" and len(sys.argv) >= 3:
        remove_ticker(sys.argv[2])
    elif cmd == "add-firm" and len(sys.argv) >= 3:
        add_firm(sys.argv[2], *sys.argv[3:4])
    elif cmd == "add-deal" and len(sys.argv) >= 4:
        add_deal(sys.argv[2], sys.argv[3], *sys.argv[4:6])
    else:
        print(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
