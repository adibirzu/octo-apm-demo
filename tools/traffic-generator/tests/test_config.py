from octo_traffic.config import TrafficConfig


def test_default_base_urls_use_current_default_hosts(monkeypatch) -> None:
    monkeypatch.delenv("OCTO_TRAFFIC_SHOP_BASE_URL", raising=False)
    monkeypatch.delenv("OCTO_TRAFFIC_CRM_BASE_URL", raising=False)

    cfg = TrafficConfig()

    assert cfg.shop_base_url == "https://shop.example.test"
    assert cfg.crm_base_url == "https://crm.example.test"
