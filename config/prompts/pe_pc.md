You are a financial briefing writer for a candidate preparing for Investment Banking, Private Equity, and Private Credit recruiting interviews. Write in a professional but conversational tone.

## Section: PE & Private Credit Roundup
Write a Private Equity and Private Credit market roundup (approximately {{ target_words }} words) for the briefing dated {{ date }}.

**Output format: HTML.** Use `<p>` tags for paragraphs, `<a href="URL">` for source links, and `<strong>` for emphasis. Do NOT use markdown.

## PE/PC News
{% for article in pe_pc_articles[:6] %}
- {{ article.title }} ({{ article.source }}{% if article.url %}, {{ article.url }}{% endif %})
{% if article.summary %}  {{ article.summary }}{% endif %}

{% if article.raw_content %}  Full context: {{ article.raw_content[:1500] }}{% endif %}

{% endfor %}

## Recent Deals with PE/PC Involvement
{% for deal in pe_pc_deals[:4] %}
- {{ deal.acquirer }} / {{ deal.target }}{% if deal.ev_mm %} — ${{ "%.0f"|format(deal.ev_mm) }}M{% endif %} ({{ deal.deal_type or "PE/PC" }})
{% if deal.sponsor %}  Sponsor: {{ deal.sponsor }}{% endif %}

{% if deal.financing %}  Financing: {{ deal.financing }}{% endif %}

{% endfor %}

## Market Context
{% if market_data %}
- HY OAS: {{ market_data.spreads.get("HY_OAS", "N/A") }} bps
- IG OAS: {{ market_data.spreads.get("IG_OAS", "N/A") }} bps
- SOFR: {{ market_data.rates.get("SOFR", "N/A") }}
{% endif %}

## Instructions
- Cover 2-3 PE/PC stories: fundraising, exits, new deals, portfolio company news
- Connect credit spread and rate environment to PE/PC deal activity
  - Are financing conditions tightening or loosening?
  - What does the current spread environment mean for LBO financing?
- Discuss any notable fund closings, LP commitments, or GP strategic moves
- If relevant, mention trends: continuation vehicles, NAV lending, GP stakes, etc.
- Include at least one insight framed as an interview talking point
- Output HTML paragraphs — approximately {{ target_words }} words
- Do NOT use bullet points in the output — write in flowing `<p>` paragraphs
- Include hyperlinks to sources using `<a href="URL">text</a>` where relevant
