const form = document.querySelector("#order-form");
const button = document.querySelector("#run-button");
const scenarios = [...document.querySelectorAll(".scenario")];
const notes = {
  normal: "A normal order should be accepted. Use this as your baseline.",
  reject: "The playground requests 81 units of SKU-42, above its demo stock of 80.",
  slow: "Inventory waits 900 ms before answering. Compare HTTP latency with model inference time.",
  fail: "Inventory returns an error for this request. Orders should report a downstream failure.",
  "model-low": "Preset applied: low demand, more stock, and a short lead time. Run it, then compare the model output with the higher-risk preset.",
  "model-high": "Preset applied: higher demand, less stock, and a longer lead time. Run it, then compare the model output with the lower-risk preset."
};
const selectedScenario = () => document.querySelector(".scenario.selected")?.dataset.scenario || "normal";

scenarios.forEach((card) => card.addEventListener("click", () => {
  scenarios.forEach((item) => {
    const active = item === card;
    item.classList.toggle("selected", active);
    item.setAttribute("aria-pressed", String(active));
  });
  const presets = {
    "model-low": { dailyDemand: 1, onHand: 400, leadDays: 1, demandVolatility: 0.5 },
    "model-high": { dailyDemand: 35, onHand: 10, leadDays: 18, demandVolatility: 4 }
  };
  if (presets[card.dataset.scenario]) {
    for (const [name, value] of Object.entries(presets[card.dataset.scenario])) {
      form.elements.namedItem(name).value = value;
    }
  }
  document.querySelector("#scenario-note").textContent = notes[card.dataset.scenario];
}));

document.querySelector("#reset-inputs").addEventListener("click", () => {
  form.reset();
  document.querySelector('[name="sku"]').value = "SKU-42";
  document.querySelector('[name="quantity"]').value = "2";
  document.querySelector('[name="dailyDemand"]').value = "8";
  document.querySelector('[name="onHand"]').value = "40";
  document.querySelector('[name="leadDays"]').value = "4";
  document.querySelector('[name="demandVolatility"]').value = "2";
});

function values() {
  const data = new FormData(form);
  return {
    sku: String(data.get("sku")).trim(),
    quantity: Number(data.get("quantity")),
    dailyDemand: Number(data.get("dailyDemand")),
    onHand: Number(data.get("onHand")),
    leadDays: Number(data.get("leadDays")),
    demandVolatility: Number(data.get("demandVolatility"))
  };
}

async function behavior(delayMs, fail) {
  const response = await fetch("/api/inventory/demo/behavior", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ delayMs, fail })
  });
  if (!response.ok) throw new Error("Could not set the Inventory demo behavior.");
}

function showResponse(status, body, scenario) {
  const box = document.querySelector("#response-box");
  const badge = document.querySelector("#result-badge");
  const isFailure = status >= 500;
  const label = isFailure ? "DEPENDENCY ERROR" : (body.status || "HTTP " + status).toUpperCase();
  badge.textContent = label;
  badge.className = "result-badge " + (isFailure ? "error" : body.status === "rejected" ? "warning" : "success");
  const fields = isFailure
    ? [["HTTP response", status + " Bad Gateway"], ["What happened", "Orders could not complete its call to Inventory."]]
    : [["Order status", body.status], ["Inventory available", String(body.inventoryAvailable)], ["Stockout risk", body.stockoutRisk], ["Model label", body.riskLabel]];
  box.innerHTML = `<div class="empty-mark ${isFailure ? "error-mark" : ""}">${isFailure ? "×" : "✓"}</div><div class="response-content"><strong>${escapeHtml(label)}</strong><dl>${fields.map(([key, value]) => `<div><dt>${escapeHtml(key)}</dt><dd>${escapeHtml(String(value))}</dd></div>`).join("")}</dl></div>`;
  const hints = {
    normal: "Open the recent Orders trace in Jaeger. Confirm it contains an Inventory call. In Grafana, compare request rate and p95 with this baseline.",
    reject: "Compare orders_rejected_total with the 5xx error graph. A stock rejection is a business result; it should not look like a service outage.",
    slow: "Find a recent trace in Jaeger. The Inventory server span should include the injected wait; the model inference span should remain much shorter.",
    fail: "Inspect the failed downstream span in Jaeger and the HTTP 5xx graph in Grafana. Then run another scenario to confirm the demo failure was reset.",
    "model-low": "Compare riskLabel and stockoutRisk with the higher-risk preset. Inspect the prediction risk counter in Prometheus and the ml.prediction attributes on the model span in Jaeger.",
    "model-high": "Compare riskLabel and stockoutRisk with the lower-risk preset. Inspect the prediction risk counter in Prometheus and the ml.prediction attributes on the model span in Jaeger."
  };
  document.querySelector("#observe-copy").textContent = hints[scenario];
}

function escapeHtml(value) {
  return value.replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
}

async function queryPrometheus(query) {
  const response = await fetch("/prometheus/api/v1/query?query=" + encodeURIComponent(query));
  if (!response.ok) throw new Error("Prometheus query failed");
  const json = await response.json();
  if (json.status !== "success") throw new Error("Prometheus returned no result");
  return json.data.result.reduce((sum, row) => sum + Number(row.value[1]), 0);
}

async function refreshMetrics() {
  const state = document.querySelector("#metrics-state");
  try {
    const [accepted, rejected, predictions] = await Promise.all([
      queryPrometheus("orders_accepted_total"),
      queryPrometheus("orders_rejected_total"),
      queryPrometheus("inventory_stockout_risk_predictions_total")
    ]);
    document.querySelector("#accepted-count").textContent = Math.round(accepted);
    document.querySelector("#rejected-count").textContent = Math.round(rejected);
    document.querySelector("#prediction-count").textContent = Math.round(predictions);
    state.textContent = "Counters from Prometheus · values may take up to 10 seconds to update";
  } catch {
    state.textContent = "Prometheus is starting or has not scraped these metrics yet";
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const scenario = selectedScenario();
  const order = values();
  if (scenario === "reject") {
    order.sku = "SKU-42";
    order.quantity = 81;
  }
  button.disabled = true;
  button.querySelector("span").textContent = "Running…";
  document.querySelector("#result-badge").textContent = "IN PROGRESS";
  document.querySelector("#result-badge").className = "result-badge pending";
  let behaviorChanged = false;
  try {
    if (scenario === "slow" || scenario === "fail") {
      await behavior(scenario === "slow" ? 900 : 0, scenario === "fail");
      behaviorChanged = true;
    }
    const response = await fetch("/api/orders", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(order)
    });
    const raw = await response.text();
    let body;
    try { body = JSON.parse(raw); } catch { body = { detail: raw }; }
    if (!response.ok) {
      if (response.status >= 500) showResponse(response.status, body, scenario);
      else throw new Error(body.message || body.detail || "Order was rejected by input validation.");
    } else {
      showResponse(response.status, body, scenario);
    }
  } catch (error) {
    document.querySelector("#result-badge").textContent = "REQUEST FAILED";
    document.querySelector("#result-badge").className = "result-badge error";
    document.querySelector("#response-box").innerHTML = `<div class="empty-mark error-mark">!</div><div><strong>Could not complete the experiment</strong><p>${escapeHtml(error.message)} Check that Docker Compose services are healthy, then try again.</p></div>`;
  } finally {
    if (behaviorChanged) {
      try { await behavior(0, false); }
      catch { document.querySelector("#metrics-state").textContent = "Warning: could not reset Inventory behavior. Run a normal experiment to check it."; }
    }
    button.disabled = false;
    button.querySelector("span").textContent = "Run experiment";
    setTimeout(refreshMetrics, 2500);
  }
});

refreshMetrics();
