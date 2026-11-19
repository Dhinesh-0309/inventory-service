#!/usr/bin/env bash
set -euo pipefail

orders_url="${ORDERS_URL:-http://localhost:8080/orders}"
requests="${REQUESTS:-60}"

for ((i = 1; i <= requests; i++)); do
  quantity=$((1 + RANDOM % 3))
  demand=$((5 + RANDOM % 20))
  on_hand=$((20 + RANDOM % 100))
  lead_days=$((1 + RANDOM % 12))
  volatility=$((1 + RANDOM % 4))
  curl --silent --show-error --output /dev/null --write-out "request ${i}: HTTP %{http_code}\n" \
    "$orders_url" \
    -H 'Content-Type: application/json' \
    -d "{\"sku\":\"SKU-42\",\"quantity\":${quantity},\"dailyDemand\":${demand},\"onHand\":${on_hand},\"leadDays\":${lead_days},\"demandVolatility\":${volatility}}"
  sleep 0.15
done
