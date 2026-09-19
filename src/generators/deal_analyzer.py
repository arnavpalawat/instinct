"""Deep deal analysis from IB, PE, and Private Credit perspectives."""

import logging
from src.generators.llm_client import LLMClient
from src.models.deal import Deal
from src.models.article import Article

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an expert financial analyst preparing deal analysis for candidates "
    "recruiting into Investment Banking, Private Equity, and Private Credit roles. "
    "Be precise, analytical, and structured. Never fabricate financial data that is "
    "not present in the source material. When making assumptions or hypothetical "
    "projections, clearly label them as such."
)

PERSPECTIVE_PROMPTS = {
    "ib_perspective": (
        "Analyze this deal from an Investment Banking advisory perspective. Address:\n"
        "1. Strategic rationale: Why is this deal happening now? What is the buyer's thesis?\n"
        "2. Valuation: How does the implied valuation (multiples, premium) compare to "
        "sector precedents? Is the price fair?\n"
        "3. Financing structure: How is the deal being financed? What are the key terms?\n"
        "4. Process considerations: What regulatory hurdles exist? Antitrust risk? "
        "Shareholder approval likelihood?\n"
        "5. Synergies: What cost or revenue synergies are likely? How realistic are they?\n\n"
        "Be specific and reference data from the sources where available. Flag any "
        "assumptions clearly."
    ),
    "pe_perspective": (
        "Analyze this deal from a Private Equity investor's perspective. Address:\n"
        "1. Equity attractiveness: Would this be an attractive PE investment? Why or why not?\n"
        "2. Return drivers: What would drive IRR and MOIC? Revenue growth, margin "
        "expansion, multiple expansion, or debt paydown?\n"
        "3. Key assumptions: What are the most fragile assumptions in the investment thesis?\n"
        "4. Value creation plan: What operational improvements could a PE sponsor implement?\n"
        "5. Exit strategy: What are realistic exit paths and timelines? "
        "Who are natural buyers?\n\n"
        "Ground your analysis in the available data. Label any hypothetical return "
        "assumptions explicitly."
    ),
    "pc_perspective": (
        "Analyze this deal from a Private Credit / leveraged finance perspective. Address:\n"
        "1. Cash flow quality: How resilient are the target's cash flows? What repays debt?\n"
        "2. Leverage: What leverage levels are implied? How does this compare to the sector?\n"
        "3. Downside protection: What happens in a recession? Identify key risks to "
        "debt service coverage.\n"
        "4. Covenant considerations: What covenants should lenders require? "
        "What structural protections matter?\n"
        "5. Credit view: Would you lend to this deal? At what spread? What are the "
        "key credit positives and negatives?\n\n"
        "Be conservative in your assessment. Flag data gaps and label assumptions."
    ),
}


class DealAnalyzer:
    """Generates comprehensive deal analysis from three financial perspectives."""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def analyze(self, deal: Deal, articles: list[Article]) -> dict:
        """Generate comprehensive deal analysis with three perspectives.

        Returns a dict with keys:
            summary, ib_perspective, pe_perspective, pc_perspective,
            sample_answer, counterargument, follow_ups
        """
        context = self._build_deal_context(deal, articles)

        result = {
            "summary": "",
            "ib_perspective": "",
            "pe_perspective": "",
            "pc_perspective": "",
            "sample_answer": "",
            "counterargument": "",
            "follow_ups": [],
        }

        # Generate deal summary
        result["summary"] = self._generate_summary(deal, context)

        # Generate each perspective
        for perspective_key in ("ib_perspective", "pe_perspective", "pc_perspective"):
            result[perspective_key] = self._generate_perspective(
                perspective_key, deal, context
            )

        # Generate sample interview answer
        result["sample_answer"] = self._generate_sample_answer(deal, context, result)

        # Generate counterargument
        result["counterargument"] = self._generate_counterargument(deal, context, result)

        # Generate follow-up questions
        result["follow_ups"] = self._generate_follow_ups(deal, context, result)

        return result

    def _build_deal_context(self, deal: Deal, articles: list[Article]) -> str:
        """Compile all known facts about the deal from the deal object and articles."""
        parts = []

        # Deal basics
        parts.append("## Deal Overview")
        parts.append(f"- Target: {deal.target}")
        parts.append(f"- Acquirer/Buyer: {deal.acquirer}")
        if deal.deal_type:
            parts.append(f"- Deal Type: {deal.deal_type}")
        if deal.ev_mm is not None:
            parts.append(f"- Enterprise Value: ${deal.ev_mm:,.0f}M")
        if deal.equity_value_mm is not None:
            parts.append(f"- Equity Value: ${deal.equity_value_mm:,.0f}M")
        if deal.ev_revenue:
            parts.append(f"- EV/Revenue: {deal.ev_revenue}")
        if deal.ev_ebitda:
            parts.append(f"- EV/EBITDA: {deal.ev_ebitda}")
        if deal.premium_pct is not None:
            parts.append(f"- Premium: {deal.premium_pct:.1f}%")
        if deal.consideration:
            parts.append(f"- Consideration: {deal.consideration}")
        if deal.financing:
            parts.append(f"- Financing: {deal.financing}")
        if deal.status:
            parts.append(f"- Status: {deal.status}")
        if deal.announced_date:
            parts.append(f"- Announced: {deal.announced_date.isoformat()}")
        if deal.expected_close:
            parts.append(f"- Expected Close: {deal.expected_close}")
        if deal.sector:
            parts.append(f"- Sector: {deal.sector}")
        if deal.seller:
            parts.append(f"- Seller: {deal.seller}")
        if deal.sponsor:
            parts.append(f"- Sponsor: {deal.sponsor}")
        if deal.target_description:
            parts.append(f"- Target Description: {deal.target_description}")
        if deal.geography:
            parts.append(f"- Geography: {deal.geography}")

        # Advisors
        if deal.advisors.get("target") or deal.advisors.get("acquirer"):
            parts.append("\n## Advisors")
            if deal.advisors.get("target"):
                parts.append(f"- Target advisors: {', '.join(deal.advisors['target'])}")
            if deal.advisors.get("acquirer"):
                parts.append(
                    f"- Acquirer advisors: {', '.join(deal.advisors['acquirer'])}"
                )

        # Related articles
        related = [
            a for a in articles if a.id in deal.source_articles or a.is_deal_related
        ]
        if related:
            parts.append("\n## Source Articles")
            for article in related[:10]:  # Cap at 10 most relevant
                parts.append(f"\n### {article.title}")
                parts.append(f"Source: {article.source} | {article.url}")
                if article.summary:
                    parts.append(article.summary)
                elif article.raw_content:
                    # Use first 1500 chars of raw content as context
                    parts.append(article.raw_content[:1500])

        return "\n".join(parts)

    def _generate_summary(self, deal: Deal, context: str) -> str:
        """Generate a concise deal summary."""
        prompt = (
            f"Based on the following deal information, write a concise 2-3 paragraph "
            f"summary of this transaction suitable for a daily financial briefing. "
            f"Cover the key facts: who, what, why, how much, and what happens next.\n\n"
            f"{context}"
        )
        result = self.llm.generate(prompt, system=SYSTEM_PROMPT, max_tokens=500)
        if not result:
            # Template fallback
            result = (
                f"{deal.acquirer} is {'acquiring' if deal.status != 'completed' else 'has acquired'} "
                f"{deal.target}"
            )
            if deal.ev_mm:
                result += f" in a deal valued at approximately ${deal.ev_mm:,.0f}M"
            if deal.deal_type:
                result += f" ({deal.deal_type})"
            result += "."
            if deal.consideration:
                result += f" The transaction is structured as {deal.consideration}."
            if deal.status:
                result += f" Status: {deal.status}."
        return result

    def _generate_perspective(
        self, perspective: str, deal: Deal, context: str
    ) -> str:
        """Generate one perspective (IB, PE, or PC) for the deal."""
        perspective_instruction = PERSPECTIVE_PROMPTS.get(perspective, "")
        prompt = (
            f"{perspective_instruction}\n\n"
            f"## Deal Information\n{context}\n\n"
            f"Write 3-5 focused paragraphs. Be analytical and specific."
        )

        result = self.llm.generate(prompt, system=SYSTEM_PROMPT, max_tokens=800)
        if not result:
            label = perspective.replace("_", " ").title()
            result = (
                f"[{label} analysis unavailable — LLM generation failed. "
                f"Key data points: {deal.target} / {deal.acquirer}"
            )
            if deal.ev_mm:
                result += f", EV ${deal.ev_mm:,.0f}M"
            if deal.ev_ebitda:
                result += f", {deal.ev_ebitda} EV/EBITDA"
            result += "]"
        return result

    def _generate_sample_answer(
        self, deal: Deal, context: str, analysis: dict
    ) -> str:
        """Generate a 60-90 second 'deal I'm following' interview answer."""
        prompt = (
            f"Using the deal information and analysis below, write a sample interview "
            f"answer for the question: 'Tell me about a deal you're following.'\n\n"
            f"The answer should be:\n"
            f"- 150-225 words (roughly 60-90 seconds spoken)\n"
            f"- Structured as: (1) Deal overview in one sentence, (2) Why it's "
            f"interesting, (3) Your opinion with reasoning, (4) One thing you're "
            f"watching going forward\n"
            f"- Confident but not arrogant, showing genuine analytical interest\n"
            f"- Grounded in facts from the sources\n\n"
            f"## Deal Information\n{context}\n\n"
            f"## Summary\n{analysis.get('summary', '')}\n\n"
            f"Write the answer in first person, as if the candidate is speaking."
        )
        result = self.llm.generate(prompt, system=SYSTEM_PROMPT, max_tokens=500)
        if not result:
            result = (
                f"I've been following the {deal.acquirer} acquisition of {deal.target}. "
                f"It's a {deal.deal_type or 'strategic'} transaction"
            )
            if deal.ev_mm:
                result += f" valued at around ${deal.ev_mm:,.0f} million"
            result += (
                ". I find it interesting because of the strategic rationale and "
                "the current market dynamics. I'm watching how the regulatory "
                "review process unfolds and whether the deal closes on the "
                "expected timeline."
            )
        return result

    def _generate_counterargument(
        self, deal: Deal, context: str, analysis: dict
    ) -> str:
        """Generate a counterargument to the deal thesis."""
        prompt = (
            f"Based on the deal information below, present the strongest "
            f"counterargument or bear case against this transaction. "
            f"Consider: integration risk, overpayment risk, regulatory risk, "
            f"market timing, strategic fit concerns, or execution challenges.\n\n"
            f"Write 2-3 concise paragraphs that a candidate could use to show "
            f"critical thinking in an interview.\n\n"
            f"## Deal Information\n{context}\n\n"
            f"## Analysis Summary\n{analysis.get('summary', '')}"
        )
        result = self.llm.generate(prompt, system=SYSTEM_PROMPT, max_tokens=400)
        if not result:
            result = (
                f"The primary risk in the {deal.acquirer}-{deal.target} deal is "
                f"execution and integration. "
            )
            if deal.premium_pct and deal.premium_pct > 30:
                result += (
                    f"The {deal.premium_pct:.0f}% premium paid may prove difficult "
                    f"to justify if synergy realization falls short of projections. "
                )
            result += (
                "Additionally, regulatory scrutiny could delay or block the "
                "transaction, and market conditions may shift during the review period."
            )
        return result

    def _generate_follow_ups(
        self, deal: Deal, context: str, analysis: dict
    ) -> list[dict]:
        """Generate 2 likely interviewer follow-up questions with suggested answers."""
        prompt = (
            f"Based on the deal below, generate exactly 2 likely follow-up "
            f"questions an interviewer might ask after a candidate discusses "
            f"this deal. For each, provide:\n"
            f"1. The question\n"
            f"2. A suggested answer (3-4 sentences)\n\n"
            f"Format as:\n"
            f"Q1: [question]\n"
            f"A1: [answer]\n\n"
            f"Q2: [question]\n"
            f"A2: [answer]\n\n"
            f"Focus on questions that test analytical thinking: valuation, "
            f"financing, strategic logic, or market dynamics.\n\n"
            f"## Deal Information\n{context}\n\n"
            f"## Analysis Summary\n{analysis.get('summary', '')}"
        )
        result = self.llm.generate(prompt, system=SYSTEM_PROMPT, max_tokens=600)

        follow_ups = []
        if result:
            follow_ups = self._parse_follow_ups(result)

        # Ensure we always have at least 2 follow-ups
        if len(follow_ups) < 2:
            defaults = [
                {
                    "question": f"How would you think about the valuation of {deal.target}?",
                    "answer": (
                        f"I would look at comparable transactions in the "
                        f"{deal.sector or 'sector'} and compare the implied multiples. "
                        f"Key considerations include the target's growth profile, "
                        f"margin trajectory, and the strategic premium justified "
                        f"by synergies."
                    ),
                },
                {
                    "question": "What risks could prevent this deal from closing?",
                    "answer": (
                        "The main risks are regulatory approval, particularly "
                        "antitrust review, financing conditions if markets deteriorate, "
                        "and shareholder approval. Any material adverse change in the "
                        "target's business could also trigger MAC clause concerns."
                    ),
                },
            ]
            for d in defaults:
                if len(follow_ups) < 2:
                    follow_ups.append(d)

        return follow_ups[:2]

    @staticmethod
    def _parse_follow_ups(text: str) -> list[dict]:
        """Parse Q&A pairs from LLM output."""
        follow_ups = []
        lines = text.strip().split("\n")
        current_q = ""
        current_a = ""

        for line in lines:
            stripped = line.strip()
            if stripped.startswith(("Q1:", "Q2:", "Q3:")):
                if current_q and current_a:
                    follow_ups.append(
                        {"question": current_q.strip(), "answer": current_a.strip()}
                    )
                current_q = stripped.split(":", 1)[1].strip()
                current_a = ""
            elif stripped.startswith(("A1:", "A2:", "A3:")):
                current_a = stripped.split(":", 1)[1].strip()
            elif current_a is not None and stripped:
                # Continuation line for the current answer
                if current_a:
                    current_a += " " + stripped
                elif current_q:
                    current_q += " " + stripped

        # Don't forget the last pair
        if current_q and current_a:
            follow_ups.append(
                {"question": current_q.strip(), "answer": current_a.strip()}
            )

        return follow_ups
