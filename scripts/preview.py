#!/usr/bin/env python3
"""Render the page template with mock data and open in browser.

Usage:  python3 scripts/preview.py
        python3 scripts/preview.py --no-open   # write file only, don't open browser
"""
import os
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

# ── Mock data ────────────────────────────────────────────────────────

DATE = datetime.now().strftime("%Y-%m-%d")
DATE_FMT = datetime.now().strftime("%a, %b %d, %Y")

SECTION_LABELS = {
    "opening_brief": "Opening Brief",
    "markets_macro": "Markets & Macro",
    "deal_of_day": "Deal of the Day",
    "pe_pc": "PE & PC Developments",
    "company_insight": "Company / Sector Insight",
    "politics_policy": "Politics & Policy",
    "interview_practice": "Interview Practice",
    "what_to_watch": "What to Watch",
}
SECTION_ORDER = list(SECTION_LABELS.keys())

SECTIONS = {
    "opening_brief": """
        <p><strong>Markets rallied sharply</strong> as the Federal Reserve signaled a
        potential pause in rate hikes. The S&amp;P 500 rose 1.2% while the 10-year
        yield fell 8 basis points to 4.15%. A landmark $28B acquisition in the
        healthcare sector dominated deal flow.</p>
        <p>Private equity fundraising continued at a robust pace, with three major
        funds closing above target. Credit spreads tightened modestly, suggesting
        improved risk appetite across leveraged finance markets.</p>
    """,
    "markets_macro": """
        <p>U.S. equities posted broad gains on Thursday as investors digested the
        latest batch of economic data. The <strong>S&amp;P 500</strong> gained 1.2%,
        led by technology and healthcare names, while the <strong>Nasdaq</strong>
        outperformed with a 1.5% advance.</p>
        <p>Treasury yields moved lower across the curve. The 10-year note settled at
        4.150%, down 8 basis points, as traders priced in a higher probability of a
        December rate cut. The 2s/10s spread steepened to 15 basis points.</p>
        <p>In credit markets, investment-grade spreads tightened 3 basis points to
        95 bps over Treasuries, while high-yield spreads compressed to 340 bps.
        Primary issuance was heavy, with $15B in new IG deals.</p>
    """,
    "deal_of_day": """
        <p><strong>MedTech Corp announced a definitive agreement to acquire HealthCo
        for $28 billion</strong> in an all-cash transaction, representing a 35%
        premium to HealthCo's undisturbed price. The deal values HealthCo at
        approximately 18x forward EBITDA.</p>
        <p>Goldman Sachs and Morgan Stanley are advising MedTech, while J.P. Morgan
        and Centerview Partners represent HealthCo. Financing includes a $20B bridge
        facility led by the advisory banks.</p>
    """,
    "pe_pc": """
        <p>Apollo Global Management closed its latest flagship fund at $30 billion,
        exceeding its $25 billion target. The fund will focus on large-cap buyouts
        across industrials, financial services, and technology.</p>
        <p>In private credit, Ares Management priced a $2.5 billion direct lending
        facility for a sponsor-backed software company at SOFR + 575 bps with a
        1.5% OID, reflecting continued strong demand for floating-rate assets.</p>
    """,
    "company_insight": """
        <p><strong>NVIDIA reported Q3 earnings</strong> that beat expectations on
        both revenue and EPS. Data center revenue surged 280% year-over-year to
        $14.5 billion, driven by AI infrastructure demand.</p>
        <p>Management raised Q4 guidance above consensus, projecting $20 billion in
        revenue. The stock rose 5% in after-hours trading.</p>
    """,
    "politics_policy": """
        <p>The <strong>Federal Trade Commission unveiled new merger guidelines</strong>
        that could significantly impact deal-making in the technology and healthcare
        sectors. The updated framework lowers the thresholds for presumptive antitrust
        challenges and introduces new tests for vertical mergers.</p>
        <p>For investment banking candidates, this is a critical regulatory development:
        the new guidelines may slow large-cap M&amp;A and increase the importance of
        antitrust counsel in deal structuring. Expect more divestitures and remedy
        packages as conditions of approval.</p>
        <p>Meanwhile, Congress advanced a bipartisan infrastructure spending bill that
        could unlock $200 billion in new project financing, creating opportunities for
        infrastructure-focused PE funds and project finance teams.</p>
    """,
    "interview_practice": """
        <div class="qa-item">
            <div class="qa-question">Walk me through the key considerations when
            financing a $28B healthcare acquisition.</div>
            <button class="qa-reveal-btn">Reveal Answer</button>
            <div class="qa-answer">
                <p>For a $28B deal, you'd consider: (1) the mix of debt vs. equity —
                likely 60-70% debt given healthcare's stable cash flows; (2) the
                capital structure across senior secured, unsecured, and subordinated
                tranches; (3) rating agency considerations and target leverage of
                4-5x EBITDA; (4) bridge-to-bond strategy given the size.</p>
            </div>
        </div>
    """,
    "what_to_watch": """
        <p><strong>Next week:</strong> November jobs report (Friday) is the key
        macro event. Consensus expects 180K nonfarm payrolls with unemployment
        steady at 3.9%. A weak print could cement December rate cut expectations.</p>
        <p>Earnings: Salesforce (Tue), Dollar General (Thu). Several pending M&amp;A
        transactions approach regulatory deadlines.</p>
    """,
}

TOP_ARTICLES = [
    {
        "title": "Federal Reserve Signals Potential Rate Pause as Inflation Cools",
        "url": "https://example.com/fed-rate-pause",
        "source": "Reuters",
        "summary": "The Federal Reserve indicated it may hold rates steady at its next meeting as recent inflation data shows signs of cooling toward the 2% target.",
        "image_url": "https://picsum.photos/seed/fed/800/400",
    },
    {
        "title": "MedTech Corp to Acquire HealthCo in $28B Deal",
        "url": "https://example.com/medtech-healthco",
        "source": "Bloomberg",
        "summary": "MedTech Corp announced a definitive agreement to acquire HealthCo for $28 billion in cash.",
        "image_url": "https://picsum.photos/seed/deal/400/300",
    },
    {
        "title": "Apollo Closes $30B Flagship Buyout Fund",
        "url": "https://example.com/apollo-fund",
        "source": "WSJ",
        "summary": "Apollo Global Management closed its latest fund above its $25B target.",
        "image_url": "https://picsum.photos/seed/apollo/400/300",
    },
    {
        "title": "NVIDIA Earnings Beat as AI Demand Surges",
        "url": "https://example.com/nvidia",
        "source": "CNBC",
        "summary": "NVIDIA reported Q3 earnings that significantly exceeded Wall Street expectations.",
        "image_url": "https://picsum.photos/seed/nvidia/400/300",
    },
    {
        "title": "FTC Unveils Stricter Merger Review Guidelines",
        "url": "https://example.com/ftc-merger",
        "source": "Financial Times",
        "summary": "New FTC guidelines could reshape M&A landscape with tougher antitrust standards.",
        "image_url": "",
    },
    {
        "title": "European Central Bank Holds Rates, Signals 2024 Cut",
        "url": "https://example.com/ecb",
        "source": "Reuters",
        "summary": "The ECB kept rates unchanged but signaled potential easing in early 2024.",
        "image_url": "https://picsum.photos/seed/ecb/400/300",
    },
    {
        "title": "Private Credit Market Reaches $1.7 Trillion",
        "url": "https://example.com/private-credit",
        "source": "Bloomberg",
        "summary": "The private credit market has grown to $1.7 trillion as banks retreat from lending.",
        "image_url": "https://picsum.photos/seed/credit/400/300",
    },
]

MARKET = {
    "indices": {"S&P 500": 5234.18, "NASDAQ": 16742.39, "DJIA": 39127.14},
    "index_changes": {"S&P 500": 1.18, "NASDAQ": 1.51, "DJIA": 0.85},
    "yields": {"2Y": 4.621, "10Y": 4.150, "30Y": 4.385},
    "yield_changes_bps": {"2Y": -5.2, "10Y": -8.0, "30Y": -3.1},
    "spreads": {"IG_OAS": 95, "HY_OAS": 340},
    "rates": {"SOFR": 5.3100, "FedFunds": 5.3300},
    "fx": {"DXY": 103.42, "EURUSD": 1.0892},
    "commodities": {"WTI": 77.43, "Gold": 2045.60},
    "vix": 13.45,
}

DEALS = [
    {
        "target": "HealthCo",
        "acquirer": "MedTech Corp",
        "deal_type": "Strategic M&A",
        "ev_mm": 28000,
        "ev_revenue": "5.2x",
        "ev_ebitda": "18.0x",
        "premium_pct": 35.0,
        "consideration": "All-Cash",
        "financing": "$20B bridge facility",
        "status": "announced",
        "sector": "Healthcare",
    },
]

APPENDIX = {
    "full_market_table": "| Metric | Value | Change |\n|--------|-------|--------|\n| S&P 500 | 5,234.18 | +1.18% |\n| NASDAQ | 16,742.39 | +1.51% |",
    "additional_stories": [
        {"title": "Blackstone Eyes $5B Data Center Platform", "source": "Bloomberg", "url": "https://example.com/1", "summary": "Blackstone is in talks to acquire a major data center platform.", "image_url": "https://picsum.photos/seed/bs/160/112"},
        {"title": "KKR Closes Infrastructure Fund at $17B", "source": "WSJ", "url": "https://example.com/2", "summary": "KKR closed its fourth infrastructure fund.", "image_url": "https://picsum.photos/seed/kkr/160/112"},
        {"title": "Goldman Sachs Restructures Investment Banking Division", "source": "FT", "url": "https://example.com/3", "summary": "Goldman is reorganizing its IBD.", "image_url": ""},
        {"title": "Japan Intervenes in Currency Markets", "source": "Reuters", "url": "https://example.com/4", "summary": "BOJ intervened to support the yen.", "image_url": "https://picsum.photos/seed/japan/160/112"},
        {"title": "Carlyle Group Names New CEO", "source": "Bloomberg", "url": "https://example.com/5", "summary": "Carlyle has appointed a new chief executive.", "image_url": ""},
    ],
    "source_links": [
        {"title": "Reuters - Fed Rate Decision", "url": "https://example.com/reuters"},
        {"title": "Bloomberg - MedTech Deal", "url": "https://example.com/bloomberg"},
    ],
    "glossary_term": {"term": "Bridge Financing", "definition": "Short-term financing used to bridge the gap until permanent financing is arranged, commonly used in M&A transactions."},
    "retrieval_questions": [
        "What was the enterprise value of the MedTech/HealthCo deal?",
        "Which PE firm closed a fund above $25B this week?",
        "What is the current 10-year Treasury yield?",
    ],
}


def main():
    env = Environment(
        loader=FileSystemLoader("templates"),
        autoescape=True,
    )
    template = env.get_template("page.html")

    html = template.render(
        date_formatted=DATE_FMT,
        headline="Fed Signals Pause as $28B Healthcare Deal Reshapes M&A Landscape",
        word_count=4850,
        sections=SECTIONS,
        section_labels=SECTION_LABELS,
        section_order=SECTION_ORDER,
        appendix=APPENDIX,
        market=MARKET,
        deals=DEALS,
        top_articles=TOP_ARTICLES,
        base_url="",
        prev_date="2026-09-19",
        next_date=None,
        generated_at=datetime.now(),
        pipeline_errors=[],
    )

    out = Path("docs/_preview.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Preview written to: {out.resolve()}")

    if "--no-open" not in sys.argv:
        webbrowser.open(f"file://{out.resolve()}")


if __name__ == "__main__":
    main()
