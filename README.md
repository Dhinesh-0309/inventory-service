# Inventory Service

A FastAPI inventory management service. Used as the target application for the **Flakeless ML** CI failure triage demonstration.

## What this repo demonstrates

Every push triggers GitHub Actions CI:

1. Runs the full test suite
2. Produces JUnit XML test results
3. **Flakeless ML analyzes any failures** — classifying each as:
   - `LIKELY FLAKY` (P2) — timing/infrastructure issue
   - `POTENTIAL REGRESSION` (P1) — breaking code change
   - `INSUFFICIENT EVIDENCE` (P3) — needs more context
4. Analysis report uploaded as a CI artifact
5. Original test failure status preserved — Flakeless never masks a real bug

## Branches

| Branch | Description |
|--------|-------------|
| `main` | Stable — all tests pass |
| `feat/flaky-cache` | Introduces the timing-sensitive cache test |
| `fix/breaking-api` | Renames an endpoint — causes regression test to fail |

## Running locally

```bash
pip install -r requirements.txt
pytest tests/ --junitxml=test-results.xml -v
```

## Flakeless ML

Analysis reports are available in the **Actions** tab → select any run → **Artifacts**.
