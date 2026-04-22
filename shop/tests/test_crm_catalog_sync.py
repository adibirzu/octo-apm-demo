import pytest

from server.crm_catalog_sync import normalize_sync_action, normalize_synced_product


def test_normalize_synced_product_accepts_valid_inventory() -> None:
    product = normalize_synced_product(
        {
            "name": "Field Battery",
            "sku": "BAT-900",
            "description": "Spare pack",
            "price": 299.99,
            "stock": 22,
            "category": "Batteries",
            "image_url": "/static/img/products/bat_001.jpg",
            "is_active": 1,
        }
    )

    assert product["sku"] == "BAT-900"
    assert product["stock"] == 22
    assert product["category"] == "Batteries"


def test_normalize_synced_product_rejects_negative_stock() -> None:
    with pytest.raises(ValueError):
        normalize_synced_product(
            {
                "name": "Broken Stock",
                "sku": "BAD-900",
                "price": 10,
                "stock": -1,
            }
        )


def test_normalize_sync_action_rejects_unknown_action() -> None:
    with pytest.raises(ValueError):
        normalize_sync_action("delete")
