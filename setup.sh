#!/bin/bash
# Setup virtual environment and install dependencies

set -e

echo "Creating virtual environment..."
python3 -m venv .venv

echo "Activating virtual environment..."
source .venv/bin/activate

echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "Installing Playwright browser (Chromium)..."
playwright install chromium

echo ""
echo "✓ Setup complete!"
echo ""
echo "To activate the virtual environment in the future, run:"
echo "  source .venv/bin/activate"
echo ""
echo "To run the application:"
echo "  python apply.py --vacancy <path_or_url> --slug <position-slug>"
echo ""
