from server.shop_catalog_sync import build_shop_sync_payload


def test_build_shop_sync_payload_maps_inventory_fields() -> None:
    payload = build_shop_sync_payload(
        {
            "name": "SkyLifter X",
            "sku": "DRN-900",
            "description": "Heavy-lift drone",
            "price": 4200.5,
            "stock": 14,
            "category": "Complete Drones",
            "image_url": "/static/img/products/drn_001.jpg",
            "is_active": 1,
        }
    )

    assert payload["sku"] == "DRN-900"
    assert payload["stock"] == 14
    assert payload["price"] == 4200.5
    assert payload["is_active"] == 1


def test_build_shop_sync_payload_defaults_blank_values() -> None:
    payload = build_shop_sync_payload({"name": "Battery Pack", "sku": "BAT-900", "price": 0, "stock": 0})

    assert payload["description"] == ""
    assert payload["category"] == ""
    assert payload["image_url"] == ""
    assert payload["is_active"] == 1
