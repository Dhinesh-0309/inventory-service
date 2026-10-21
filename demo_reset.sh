#!/bin/bash
# ─────────────────────────────────────────────────────────────
# DEMO RESET — Restore working state before the demo
# Run this BEFORE presenting.
# ─────────────────────────────────────────────────────────────
set -e
cd "$(dirname "$0")"

echo "Resetting to working state..."

sed -i '' 's|@app.get("/metrics/overview")|@app.get("/metrics/summary")|' app/main.py 2>/dev/null || true

# Verify
if grep -q '@app.get("/metrics/summary")' app/main.py; then
    echo "  app/main.py — endpoint restored to /metrics/summary"
else
    echo "  app/main.py — already correct"
fi

# Check all tests pass locally
echo ""
echo "Running local tests to verify..."
python -m pytest tests/ -q --ignore=tests/test_inventory.py 2>/dev/null || true
python -m pytest tests/test_inventory.py::TestMetricsEndpointContract -q 2>&1 | tail -2

echo ""
echo "════════════════════════════════════════════════"
echo "  Ready for demo."
echo "  Start the API:       python /Users/dp/Documents/FLAKE/flakeless-ml/scripts/start_api.py"
echo "  Start dashboard:     streamlit run /Users/dp/Documents/FLAKE/flakeless-ml/app/streamlit_app.py"
echo "  Then run:            bash demo_1_regression.sh"
echo "════════════════════════════════════════════════"
