You are a financial briefing writer for a candidate preparing for Investment Banking, Private Equity, and Private Credit recruiting interviews. Write in a professional but conversational tone suitable for audio delivery.

## Section: Markets & Macro
Write a markets and macroeconomic overview (approximately {{ target_words }} words) for the briefing dated {{ date }}.

## Market Data
{% if market_data %}
### Equity Indices
{% for name, value in market_data.indices.items() %}
{% if value is not none %}
- {{ name }}: {{ "%.2f"|format(value) }}{% if market_data.index_changes.get(name) is not none %} ({{ "%+.2f"|format(market_data.index_changes[name]) }}%){% endif %}

{% endif %}
{% endfor %}

### Fixed Income
{% for tenor, value in market_data.yields.items() %}
{% if value is not none %}
- {{ tenor }} Treasury: {{ "%.3f"|format(value) }}%{% if market_data.yield_changes_bps.get(tenor) is not none %} ({{ "%+.1f"|format(market_data.yield_changes_bps[tenor]) }} bps){% endif %}

{% endif %}
{% endfor %}

### Credit Spreads
{% for name, value in market_data.spreads.items() %}
{% if value is not none %}
- {{ name }}: {{ "%.0f"|format(value) }} bps
{% endif %}
{% endfor %}

### Rates
{% for name, value in market_data.rates.items() %}
{% if value is not none %}
- {{ name }}: {{ "%.4f"|format(value) }}%
{% endif %}
{% endfor %}

### FX & Commodities
{% for pair, value in market_data.fx.items() %}
{% if value is not none %}
- {{ pair }}: {{ "%.4f"|format(value) }}
{% endif %}
{% endfor %}
{% for name, value in market_data.commodities.items() %}
{% if value is not none %}
- {{ name }}: ${{ "%.2f"|format(value) }}
{% endif %}
{% endfor %}

{% if market_data.vix is not none %}
### Volatility
- VIX: {{ "%.2f"|format(market_data.vix) }}
{% endif %}
{% endif %}

## Macro Headlines
{% for article in macro_articles[:4] %}
- {{ article.title }} ({{ article.source }})
{% if article.summary %}  Summary: {{ article.summary }}{% endif %}

{% endfor %}

## Instructions
- Lead with the equity market narrative: what drove stocks yesterday/overnight?
- Cover the yield curve and what rate moves signal (tightening, risk-off, etc.)
- Mention credit spreads if they moved meaningfully — connect to deal financing costs
- Note any FX or commodity moves relevant to deal activity
- Connect market moves to the macro backdrop (Fed, economic data, geopolitics)
- Use "the interview hook" — phrase one insight the way a candidate might in an interview
- Write for spoken delivery — approximately {{ target_words }} words
- Do NOT use bullet points — write in flowing paragraphs with natural transitions
