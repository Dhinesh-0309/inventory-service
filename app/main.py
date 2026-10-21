"""
Inventory Service — FastAPI application.
Target app for Flakeless ML CI failure triage demonstration.
"""
from __future__ import annotations

from typing import Optional
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

app = FastAPI(title="Inventory Service", version="1.0.0")

# In-memory store
_inventory: dict[int, dict] = {
    1: {"id": 1, "name": "Widget A", "quantity": 100, "price": 9.99,  "active": True},
    2: {"id": 2, "name": "Widget B", "quantity": 50,  "price": 19.99, "active": True},
    3: {"id": 3, "name": "Widget C", "quantity": 0,   "price": 4.99,  "active": False},
}
_next_id = 4


class ItemCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    quantity: int = Field(..., ge=0)
    price: float = Field(..., gt=0)
    active: bool = True


class ItemUpdate(BaseModel):
    quantity: Optional[int] = Field(None, ge=0)
    price: Optional[float] = Field(None, gt=0)
    active: Optional[bool] = None


class Item(BaseModel):
    id: int
    name: str
    quantity: int
    price: float
    active: bool


@app.get("/health")
def health():
    return {"status": "ok", "service": "inventory-service"}


@app.get("/items", response_model=list[Item])
def list_items(active_only: bool = False):
    items = list(_inventory.values())
    if active_only:
        items = [i for i in items if i["active"]]
    return items


@app.get("/items/{item_id}", response_model=Item)
def get_item(item_id: int):
    if item_id not in _inventory:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
    return _inventory[item_id]


@app.post("/items", response_model=Item, status_code=status.HTTP_201_CREATED)
def create_item(payload: ItemCreate):
    global _next_id
    item = {"id": _next_id, **payload.model_dump()}
    _inventory[_next_id] = item
    _next_id += 1
    return item


@app.patch("/items/{item_id}", response_model=Item)
def update_item(item_id: int, payload: ItemUpdate):
    if item_id not in _inventory:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
    item = _inventory[item_id]
    updates = payload.model_dump(exclude_none=True)
    item.update(updates)
    return item


@app.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: int):
    if item_id not in _inventory:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
    del _inventory[item_id]


@app.get("/items/{item_id}/stock-status")
def stock_status(item_id: int):
    if item_id not in _inventory:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
    item = _inventory[item_id]
    if item["quantity"] == 0:
        level = "out_of_stock"
    elif item["quantity"] < 10:
        level = "low_stock"
    else:
        level = "in_stock"
    return {"item_id": item_id, "quantity": item["quantity"], "level": level}


@app.get("/metrics/overview")
def metrics_summary():
    items = list(_inventory.values())
    total = len(items)
    active = sum(1 for i in items if i["active"])
    out_of_stock = sum(1 for i in items if i["quantity"] == 0)
    total_value = sum(i["quantity"] * i["price"] for i in items)
    return {
        "total_items": total,
        "active_items": active,
        "out_of_stock": out_of_stock,
        "total_inventory_value": round(total_value, 2),
    }
