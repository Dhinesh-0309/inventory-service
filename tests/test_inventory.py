"""
Inventory Service — Test Suite

Three categories of tests for the Flakeless ML demonstration:

1. STABLE TESTS (always pass)      — normal functionality
2. FLAKY TEST (intermittent)       — timing-sensitive, fails ~30% of runs
3. REGRESSION TEST (always fails)  — broken by a recent code change
   This test is marked xfail in the stable branch and will fail
   when a breaking commit removes/renames an endpoint.
"""
import time
import random
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


# ─── Stable tests — these always pass ─────────────────────────────────────────

class TestHealthCheck:
    def test_health_endpoint_returns_ok(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_health_includes_service_name(self):
        response = client.get("/health")
        assert "service" in response.json()


class TestListItems:
    def test_list_all_items(self):
        response = client.get("/items")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        assert len(response.json()) == 3

    def test_list_active_items_only(self):
        response = client.get("/items?active_only=true")
        assert response.status_code == 200
        items = response.json()
        assert all(item["active"] for item in items)

    def test_list_items_returns_correct_fields(self):
        response = client.get("/items")
        item = response.json()[0]
        assert all(k in item for k in ["id", "name", "quantity", "price", "active"])


class TestGetItem:
    def test_get_existing_item(self):
        response = client.get("/items/1")
        assert response.status_code == 200
        assert response.json()["id"] == 1

    def test_get_nonexistent_item_returns_404(self):
        response = client.get("/items/9999")
        assert response.status_code == 404

    def test_get_item_correct_data(self):
        response = client.get("/items/1")
        data = response.json()
        assert data["name"] == "Widget A"
        assert data["quantity"] == 100


class TestCreateItem:
    def test_create_new_item(self):
        payload = {"name": "Widget D", "quantity": 25, "price": 14.99}
        response = client.post("/items", json=payload)
        assert response.status_code == 201
        assert response.json()["name"] == "Widget D"

    def test_create_item_returns_id(self):
        payload = {"name": "Widget E", "quantity": 10, "price": 7.50}
        response = client.post("/items", json=payload)
        assert "id" in response.json()

    def test_create_item_invalid_quantity_rejected(self):
        payload = {"name": "Bad Item", "quantity": -1, "price": 5.0}
        response = client.post("/items", json=payload)
        assert response.status_code == 422

    def test_create_item_invalid_price_rejected(self):
        payload = {"name": "Bad Price", "quantity": 5, "price": 0}
        response = client.post("/items", json=payload)
        assert response.status_code == 422


class TestUpdateItem:
    def test_update_quantity(self):
        response = client.patch("/items/2", json={"quantity": 75})
        assert response.status_code == 200
        assert response.json()["quantity"] == 75

    def test_update_nonexistent_item(self):
        response = client.patch("/items/9999", json={"quantity": 10})
        assert response.status_code == 404


class TestDeleteItem:
    def test_delete_existing_item(self):
        # Create a temp item to delete
        created = client.post("/items", json={"name": "Temp", "quantity": 1, "price": 1.0})
        item_id = created.json()["id"]
        response = client.delete(f"/items/{item_id}")
        assert response.status_code == 204

    def test_delete_nonexistent_item(self):
        response = client.delete("/items/99999")
        assert response.status_code == 404


class TestStockStatus:
    def test_in_stock(self):
        response = client.get("/items/1/stock-status")
        assert response.status_code == 200
        assert response.json()["level"] == "in_stock"

    def test_out_of_stock(self):
        response = client.get("/items/3/stock-status")
        assert response.status_code == 200
        assert response.json()["level"] == "out_of_stock"


class TestMetricsSummary:
    def test_summary_returns_expected_fields(self):
        response = client.get("/metrics/summary")
        assert response.status_code == 200
        data = response.json()
        assert "total_items" in data
        assert "active_items" in data
        assert "total_inventory_value" in data


# ─── Flaky test — intermittent failure ────────────────────────────────────────
# This test simulates a timing-sensitive operation.
# It fails approximately 30% of the time due to a random delay
# exceeding the threshold — exactly the kind of test Flakeless
# should classify as "Likely Flaky".

class TestInventorySyncPerformance:
    def test_bulk_read_completes_within_threshold(self):
        """
        Flaky: simulates a cache-backed bulk read that occasionally
        misses the cache and falls back to a slower path.
        In a real service this would be a network call with variable latency.
        """
        # Simulate variable latency: cache hit (~5ms) vs cache miss (~180ms)
        latency = random.choice([0.005, 0.005, 0.005, 0.005, 0.005,
                                  0.005, 0.005, 0.18,  0.005, 0.005])
        time.sleep(latency)

        start = time.time()
        response = client.get("/items")
        elapsed = time.time() - start + latency  # include the simulated latency

        assert response.status_code == 200
        # Threshold: 150ms — cache miss (~180ms) causes this to fail
        assert elapsed < 0.15, (
            f"TimeoutError: Bulk read took {elapsed*1000:.0f}ms, "
            f"expected < 150ms. Possible cache miss or slow backend."
        )


# ─── Regression test — breaks when API contract changes ───────────────────────
# This test passes on the main branch.
# When a developer pushes a commit that renames /metrics/summary
# to /metrics/overview (a breaking API change), this test fails
# with an AssertionError showing status 404 — a clear regression.

class TestMetricsEndpointContract:
    def test_metrics_summary_endpoint_exists(self):
        """
        Regression marker: verifies the /metrics/summary endpoint
        exists and returns the correct schema.
        If this endpoint is renamed or removed in a commit,
        this test fails — Flakeless should classify it as
        Potential Regression given the clean prior history.
        """
        response = client.get("/metrics/summary")
        assert response.status_code == 200, (
            f"AssertionError: /metrics/summary returned {response.status_code}. "
            "Expected 200. Endpoint may have been renamed or removed."
        )
        data = response.json()
        assert "total_inventory_value" in data, (
            "AttributeError: Response schema changed — "
            "'total_inventory_value' field missing from /metrics/summary response."
        )
