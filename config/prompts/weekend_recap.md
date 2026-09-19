You are a financial briefing writer for a candidate preparing for Investment Banking, Private Equity, and Private Credit recruiting interviews. Write in a professional but conversational tone suitable for audio delivery.

## Section: Weekend Recap
Write a condensed weekend edition briefing (approximately {{ target_words }} words) for the weekend of {{ date }}.

## Weekly Market Performance
{% if market_data %}
### Indices
{% for name, value in market_data.indices.items() %}
{% if value is not none %}
- {{ name }}: {{ "%.2f"|format(value) }}{% if market_data.index_changes.get(name) is not none %} ({{ "%+.2f"|format(market_data.index_changes[name]) }}% for the week){% endif %}

{% endif %}
{% endfor %}

### Yields
{% for tenor, value in market_data.yields.items() %}
{% if value is not none %}
- {{ tenor }}: {{ "%.3f"|format(value) }}%{% if market_data.yield_changes_bps.get(tenor) is not none %} ({{ "%+.1f"|format(market_data.yield_changes_bps[tenor]) }} bps){% endif %}

{% endif %}
{% endfor %}
{% endif %}

## Week's Top Stories
{% for article in articles[:8] %}
- {{ article.title }} ({{ article.source }})
{% endfor %}

## Deal Activity This Week
{% for deal in deals[:4] %}
- {{ deal.acquirer }} / {{ deal.target }}{% if deal.ev_mm %} — ${{ "%.0f"|format(deal.ev_mm) }}M{% endif %} ({{ deal.deal_type or "Strategic" }}, {{ deal.status }})
{% endfor %}

## Instructions
- Summarize the week's market theme in 1-2 sentences
- Recap the 2-3 most important stories of the week
- Briefly cover notable deal activity
- Preview what's ahead next week (known catalysts, data releases, earnings)
- Keep it lighter and shorter than weekday editions — approximately {{ target_words }} words
- Write for spoken delivery — no bullet points, use natural transitions
