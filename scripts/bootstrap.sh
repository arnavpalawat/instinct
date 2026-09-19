#!/bin/bash
# Instinct — First-time setup guide
set -e

echo "============================================"
echo "  INSTINCT — Daily Financial Briefing Setup"
echo "============================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is required. Install from python.org"
    exit 1
fi
echo "✓ Python 3 found: $(python3 --version)"

# Create virtual environment
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi
echo "✓ Virtual environment ready"

# Activate and install
source .venv/bin/activate
pip install -r requirements.txt --quiet
echo "✓ Dependencies installed"

echo ""
echo "============================================"
echo "  API Keys Required (all free)"
echo "============================================"
echo ""
echo "Set these as GitHub Actions secrets OR in a .env file for local testing:"
echo ""
echo "1. GROQ_API_KEY        — console.groq.com (free signup)"
echo "2. FINNHUB_API_KEY     — finnhub.io (free signup)"
echo "3. FRED_API_KEY         — fred.stlouisfed.org/docs/api/api_key.html"
echo "4. FMP_API_KEY          — financialmodelingprep.com (free signup)"
echo "5. RESEND_API_KEY       — resend.com (free, 100 emails/day)"
echo "6. RECIPIENT_EMAIL      — your email address"
echo "7. GOOGLE_TTS_CREDENTIALS — GCP service account JSON (optional, for audio)"
echo ""
echo "For local testing, create a .env file:"
echo "  cp .env.example .env"
echo "  # Edit .env with your keys"
echo ""
echo "To run locally:"
echo "  source .venv/bin/activate"
echo "  python -m src.pipeline --dry-run"
echo ""
echo "============================================"
