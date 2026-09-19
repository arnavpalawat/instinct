"""Interview preparation content generator."""

import logging
from src.generators.llm_client import LLMClient
from src.models.deal import Deal
from src.models.market_snapshot import MarketSnapshot
from src.models.article import Article

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a coach helping a candidate prepare for Investment Banking, Private "
    "Equity, and Private Credit interviews. Your role is to help them articulate "
    "intelligent, well-informed views on current deals and markets. Answers should "
    "be concise, confident, and grounded in facts. Never fabricate data."
)


class InterviewPrepGenerator:
    """Generates interview preparation content tied to the day's briefing."""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def generate(
        self,
        deal: Deal,
        deal_analysis: dict,
        market: MarketSnapshot,
        articles: list[Article],
    ) -> dict:
        """Generate interview preparation content.

        Returns a dict with keys:
            sample_answer: 60-90 second 'deal I'm following' template
            opinion: Defensible opinion + counterargument
            follow_ups: 2 likely interviewer follow-ups with suggested answers
            market_view: Sample 'what's your market view?' answer
            retrieval_questions: 3 factual questions with answers (for appendix)
        """
        result = {
            "sample_answer": "",
            "opinion": "",
            "follow_ups": [],
            "market_view": "",
            "retrieval_questions": [],
        }

        market_context = self._build_market_context(market)
        deal_context = self._build_deal_context(deal, deal_analysis)

        # Reuse deal analysis sample answer if available, otherwise generate fresh
        if deal_analysis.get("sample_answer"):
            result["sample_answer"] = deal_analysis["sample_answer"]
        else:
            result["sample_answer"] = self._generate_sample_answer(
                deal, deal_context
            )

        result["opinion"] = self._generate_opinion(deal, deal_context)

        # Reuse follow-ups from deal analysis or generate new ones
        if deal_analysis.get("follow_ups"):
            result["follow_ups"] = deal_analysis["follow_ups"]
        else:
            result["follow_ups"] = self._generate_follow_ups(deal, deal_context)

        result["market_view"] = self._generate_market_view(market, market_context)

        result["retrieval_questions"] = self._generate_retrieval_questions(
            deal, deal_context, market, market_context, articles
        )

        return result

    def _build_market_context(self, market: MarketSnapshot) -> str:
        """Build a text summary of current market conditions."""
        parts = ["## Current Market Snapshot"]

        # Indices
        for name, value in market.indices.items():
            if value is not None:
                change = market.index_changes.get(name)
                change_str = f" ({change:+.2f}%)" if change is not None else ""
                parts.append(f"- {name}: {value:,.2f}{change_str}")

        # Yields
        for tenor, value in market.yields.items():
            if value is not None:
                bps = market.yield_changes_bps.get(tenor)
                bps_str = f" ({bps:+.1f} bps)" if bps is not None else ""
                parts.append(f"- {tenor} Treasury: {value:.3f}%{bps_str}")

        # Credit spreads
        for name, value in market.spreads.items():
            if value is not None:
                parts.append(f"- {name}: {value:.0f} bps")

        # VIX
        if market.vix is not None:
            parts.append(f"- VIX: {market.vix:.2f}")

        # FX
        for pair, value in market.fx.items():
            if value is not None:
                parts.append(f"- {pair}: {value:.4f}")

        # Commodities
        for name, value in market.commodities.items():
            if value is not None:
                parts.append(f"- {name}: ${value:,.2f}")

        return "\n".join(parts)

    def _build_deal_context(self, deal: Deal, deal_analysis: dict) -> str:
        """Build text context combining deal data and analysis."""
        parts = [f"## Deal: {deal.acquirer} / {deal.target}"]
        if deal.deal_type:
            parts.append(f"Type: {deal.deal_type}")
        if deal.ev_mm is not None:
            parts.append(f"Enterprise Value: ${deal.ev_mm:,.0f}M")
        if deal.ev_ebitda:
            parts.append(f"EV/EBITDA: {deal.ev_ebitda}")
        if deal.consideration:
            parts.append(f"Consideration: {deal.consideration}")
        if deal.sector:
            parts.append(f"Sector: {deal.sector}")
        if deal.status:
            parts.append(f"Status: {deal.status}")

        if deal_analysis.get("summary"):
            parts.append(f"\n## Analysis Summary\n{deal_analysis['summary']}")

        return "\n".join(parts)

    def _generate_sample_answer(self, deal: Deal, deal_context: str) -> str:
        """Generate a 60-90 second 'deal I'm following' answer."""
        prompt = (
            f"Write a sample interview answer for: 'Tell me about a deal you're "
            f"following.' The answer should be 150-225 words (60-90 seconds spoken), "
            f"structured as:\n"
            f"1. One-sentence deal overview\n"
            f"2. Why it's interesting\n"
            f"3. Your opinion with reasoning\n"
            f"4. What you're watching next\n\n"
            f"Write in first person. Be confident and analytical.\n\n"
            f"{deal_context}"
        )
        result = self.llm.generate(prompt, system=SYSTEM_PROMPT, max_tokens=500)
        if not result:
            result = (
                f"I've been following {deal.acquirer}'s "
                f"{'acquisition of' if deal.deal_type != 'Merger' else 'merger with'} "
                f"{deal.target}."
            )
            if deal.ev_mm:
                result += f" It's valued at approximately ${deal.ev_mm:,.0f} million"
                if deal.ev_ebitda:
                    result += f" or {deal.ev_ebitda} EV/EBITDA"
                result += "."
            result += (
                " I find it interesting because of the strategic rationale and "
                "what it signals about the broader market environment. "
                "Going forward, I'm watching the regulatory review and whether "
                "the expected synergies are realistic."
            )
        return result

    def _generate_opinion(self, deal: Deal, deal_context: str) -> str:
        """Generate a defensible opinion with counterargument."""
        prompt = (
            f"Based on the deal below, write a defensible opinion a candidate could "
            f"express in an interview. Structure it as:\n\n"
            f"**My view:** [2-3 sentences stating a clear opinion on the deal — "
            f"e.g., whether it's a good deal, fairly priced, strategically sound]\n\n"
            f"**Key supporting points:** [2-3 bullet points]\n\n"
            f"**Strongest counterargument:** [2-3 sentences presenting the best "
            f"opposing view]\n\n"
            f"**How I'd respond:** [1-2 sentences addressing the counterargument]\n\n"
            f"The opinion should be nuanced and show critical thinking, not just "
            f"'the deal is good/bad.'\n\n"
            f"{deal_context}"
        )
        result = self.llm.generate(prompt, system=SYSTEM_PROMPT, max_tokens=600)
        if not result:
            result = (
                f"My view: The {deal.acquirer}-{deal.target} transaction "
                f"{'appears strategically sound' if deal.premium_pct is None or deal.premium_pct < 40 else 'carries execution risk given the premium paid'}. "
                f"The strongest counterargument centers on integration risk and "
                f"whether projected synergies will materialize on schedule."
            )
        return result

    def _generate_follow_ups(
        self, deal: Deal, deal_context: str
    ) -> list[dict]:
        """Generate 2 follow-up questions with answers."""
        prompt = (
            f"Generate 2 follow-up questions an interviewer might ask after "
            f"a candidate discusses this deal, with suggested answers.\n\n"
            f"Format exactly as:\n"
            f"Q1: [question]\n"
            f"A1: [answer in 3-4 sentences]\n\n"
            f"Q2: [question]\n"
            f"A2: [answer in 3-4 sentences]\n\n"
            f"{deal_context}"
        )
        result = self.llm.generate(prompt, system=SYSTEM_PROMPT, max_tokens=500)

        follow_ups = []
        if result:
            follow_ups = self._parse_qa_pairs(result)

        if len(follow_ups) < 2:
            defaults = [
                {
                    "question": f"How would you value {deal.target} independently?",
                    "answer": (
                        f"I would use a DCF analysis alongside comparable company "
                        f"and precedent transaction multiples in the "
                        f"{deal.sector or 'relevant'} sector. Key drivers would "
                        f"include revenue growth trajectory, margin profile, and "
                        f"capital intensity."
                    ),
                },
                {
                    "question": "What could go wrong with this deal?",
                    "answer": (
                        "The primary risks are regulatory pushback, "
                        "integration complexity, and potential synergy shortfalls. "
                        "If the macro environment deteriorates, financing terms "
                        "could also become more challenging."
                    ),
                },
            ]
            for d in defaults:
                if len(follow_ups) < 2:
                    follow_ups.append(d)

        return follow_ups[:2]

    def _generate_market_view(
        self, market: MarketSnapshot, market_context: str
    ) -> str:
        """Generate a sample 'what's your market view?' answer."""
        prompt = (
            f"Using the market data below, write a sample interview answer for: "
            f"'What's your view on the current market environment?'\n\n"
            f"The answer should be:\n"
            f"- 120-180 words (roughly 50-70 seconds spoken)\n"
            f"- Cover: equity markets, rates/yields, credit conditions, and "
            f"implications for deal activity\n"
            f"- Show awareness of the macro backdrop\n"
            f"- Include a forward-looking view\n"
            f"- Be balanced — acknowledge both risks and opportunities\n\n"
            f"Write in first person.\n\n"
            f"{market_context}"
        )
        result = self.llm.generate(prompt, system=SYSTEM_PROMPT, max_tokens=400)
        if not result:
            # Template fallback using available data
            parts = ["Looking at the current market environment, "]
            if market.indices.get("SP500"):
                sp_change = market.index_changes.get("SP500")
                if sp_change is not None:
                    direction = "up" if sp_change > 0 else "down"
                    parts.append(
                        f"the S&P 500 is {direction} {abs(sp_change):.1f}% recently. "
                    )
            if market.yields.get("10Y"):
                parts.append(
                    f"The 10-year Treasury yield sits at {market.yields['10Y']:.2f}%, "
                )
                if market.yields.get("2Y"):
                    spread = market.yields["10Y"] - market.yields["2Y"]
                    curve = "inverted" if spread < 0 else "positively sloped"
                    parts.append(f"with the yield curve {curve}. ")
            parts.append(
                "I think the environment remains constructive for deal activity, "
                "though sponsors are being selective given current valuations "
                "and financing costs."
            )
            result = "".join(parts)
        return result

    def _generate_retrieval_questions(
        self,
        deal: Deal,
        deal_context: str,
        market: MarketSnapshot,
        market_context: str,
        articles: list[Article],
    ) -> list[dict]:
        """Generate 3 factual questions with answers for self-testing."""
        # Build article headlines for context
        article_context = ""
        if articles:
            headlines = [
                f"- {a.title} ({a.source})" for a in articles[:8] if a.title
            ]
            if headlines:
                article_context = (
                    "\n## Today's Headlines\n" + "\n".join(headlines)
                )

        prompt = (
            f"Based on today's briefing data below, generate exactly 3 factual "
            f"retrieval questions that test whether the reader absorbed key "
            f"information. Each question should have a clear, specific answer.\n\n"
            f"Format exactly as:\n"
            f"Q1: [question]\n"
            f"A1: [answer — 1-2 sentences]\n\n"
            f"Q2: [question]\n"
            f"A2: [answer — 1-2 sentences]\n\n"
            f"Q3: [question]\n"
            f"A3: [answer — 1-2 sentences]\n\n"
            f"Mix deal-specific, market, and news questions.\n\n"
            f"{deal_context}\n\n{market_context}\n\n{article_context}"
        )
        result = self.llm.generate(prompt, system=SYSTEM_PROMPT, max_tokens=500)

        questions = []
        if result:
            questions = self._parse_qa_pairs(result)

        # Ensure we have 3 questions
        if len(questions) < 3:
            defaults = [
                {
                    "question": f"What is the enterprise value of the {deal.acquirer}-{deal.target} deal?",
                    "answer": (
                        f"${deal.ev_mm:,.0f} million."
                        if deal.ev_mm
                        else "The enterprise value was not disclosed."
                    ),
                },
                {
                    "question": "Where is the 10-year Treasury yield trading?",
                    "answer": (
                        f"The 10-year yield is at {market.yields.get('10Y', 'N/A')}%."
                        if market.yields.get("10Y")
                        else "10-year Treasury yield data was not available."
                    ),
                },
                {
                    "question": f"What type of transaction is the {deal.target} deal?",
                    "answer": (
                        f"It is a {deal.deal_type} transaction with "
                        f"{deal.consideration or 'undisclosed'} consideration."
                        if deal.deal_type
                        else f"The deal type for {deal.target} was not specified."
                    ),
                },
            ]
            for d in defaults:
                if len(questions) < 3:
                    questions.append(d)

        return questions[:3]

    @staticmethod
    def _parse_qa_pairs(text: str) -> list[dict]:
        """Parse Q&A pairs from LLM output."""
        pairs = []
        lines = text.strip().split("\n")
        current_q = ""
        current_a = ""

        for line in lines:
            stripped = line.strip()
            if stripped.startswith(("Q1:", "Q2:", "Q3:", "Q4:", "Q5:")):
                if current_q and current_a:
                    pairs.append(
                        {"question": current_q.strip(), "answer": current_a.strip()}
                    )
                current_q = stripped.split(":", 1)[1].strip()
                current_a = ""
            elif stripped.startswith(("A1:", "A2:", "A3:", "A4:", "A5:")):
                current_a = stripped.split(":", 1)[1].strip()
            elif stripped:
                if current_a:
                    current_a += " " + stripped
                elif current_q:
                    current_q += " " + stripped

        if current_q and current_a:
            pairs.append(
                {"question": current_q.strip(), "answer": current_a.strip()}
            )

        return pairs
