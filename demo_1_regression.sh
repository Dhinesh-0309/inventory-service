#!/bin/bash
# ─────────────────────────────────────────────────────────────
# DEMO ACT 1 — Introduce a Regression
# Run this live during the presentation.
# ─────────────────────────────────────────────────────────────
set -e
cd "$(dirname "$0")"

echo ""
echo "Making a breaking code change..."
echo "Renaming /metrics/summary → /metrics/overview in app/main.py"
echo ""

sed -i '' 's|@app.get("/metrics/summary")|@app.get("/metrics/overview")|' app/main.py

echo "Changed line:"
grep "@app.get.*metrics" app/main.py

git add app/main.py
git commit -m "refactor: rename /metrics/summary to /metrics/overview

Updating endpoint naming convention for API v2 consistency.
All internal callers updated."

git push origin main

echo ""
echo "════════════════════════════════════════════════"
echo "  PUSHED TO GITHUB"
echo "  Go to: https://github.com/Dhinesh-0309/inventory-service/actions"
echo "  Watch CI run → it will go RED"
echo "  Download artifact → upload test-results.xml to Flakeless dashboard"
echo "════════════════════════════════════════════════"
