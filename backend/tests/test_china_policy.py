"""M4.1：中国国界多边形、边境缓冲与 trip_type 策略"""
import asyncio

from app.services import geocode_service
from app.services.geocode_service import (
    GeoLocation,
    allow_geocode_online,
    get_location,
    is_china_anomaly,
    is_in_china,
    is_within_china_buffer,
)


def test_china_polygon_known_points():
    assert is_in_china(39.9042, 116.4074) is True      # 北京
    assert is_in_china(52.97, 122.53) is True          # 漠河
    assert is_in_china(31.23, 121.47) is True          # 上海
    assert is_in_china(29.65, 91.14) is True           # 拉萨
    assert is_in_china(37.57, 126.98) is False         # 首尔
    assert is_in_china(21.03, 105.85) is False         # 河内
    assert is_in_china(47.89, 106.91) is False         # 乌兰巴托
    assert is_in_china(43.12, 131.89) is False         # 海参崴


def test_border_buffer_for_tianchi():
    # 长白山天池中心在线界上，精确多边形可能判为境外
    assert is_in_china(42.00, 128.06) is False
    assert is_within_china_buffer(42.00, 128.06, 50) is True
    assert allow_geocode_online(42.00, 128.06, "domestic") is True
    assert allow_geocode_online(42.00, 128.06, "mixed") is False


def test_trip_type_abroad_foreign_forces_offline(monkeypatch):
    calls = []

    async def fake_gaode(lat, lon, key):
        calls.append((lat, lon))
        return GeoLocation(city="首尔", source="gaode")

    monkeypatch.setattr(geocode_service, "reverse_geocode_gaode", fake_gaode)
    monkeypatch.setattr(
        geocode_service,
        "reverse_geocode_offline",
        lambda lat, lon: GeoLocation(country="韩国", country_code="KR", city="Seoul", source="offline"),
    )

    loc, called = asyncio.run(
        get_location(37.57, 126.98, gaode_api_key="k", trip_type="abroad")
    )
    assert calls == []
    assert called is False
    assert loc.country_code == "KR"


def test_trip_type_abroad_china_coordinate_is_resolved_but_anomalous(monkeypatch):
    calls = []

    async def fake_gaode(lat, lon, key):
        calls.append((lat, lon))
        return GeoLocation(
            province="北京市", city="北京市", poi="天安门", source="gaode"
        )

    monkeypatch.setattr(geocode_service, "reverse_geocode_gaode", fake_gaode)
    monkeypatch.setattr(
        geocode_service,
        "reverse_geocode_offline",
        lambda lat, lon: GeoLocation(country="中国", country_code="CN", city="Beijing", source="offline"),
    )

    loc, called = asyncio.run(
        get_location(39.9042, 116.4074, gaode_api_key="k", trip_type="abroad")
    )
    assert calls == [(39.9042, 116.4074)]
    assert called is True
    assert loc.poi == "天安门"
    assert is_china_anomaly(39.9042, 116.4074, "abroad") is True


def test_trip_type_mixed_skips_foreign_coordinates(monkeypatch):
    calls = []

    async def fake_gaode(lat, lon, key):
        calls.append((lat, lon))
        return GeoLocation(city="首尔", source="gaode")

    monkeypatch.setattr(geocode_service, "reverse_geocode_gaode", fake_gaode)
    monkeypatch.setattr(
        geocode_service,
        "reverse_geocode_offline",
        lambda lat, lon: GeoLocation(country="韩国", country_code="KR", city="Seoul", source="offline"),
    )

    loc, called = asyncio.run(
        get_location(37.57, 126.98, gaode_api_key="k", trip_type="mixed")
    )
    assert calls == []
    assert called is False
    assert loc.country_code == "KR"


def test_trip_type_domestic_calls_gaode_inside_china(monkeypatch):
    calls = []

    async def fake_gaode(lat, lon, key):
        calls.append((lat, lon))
        return GeoLocation(
            province="北京市",
            city="北京市",
            district="东城区",
            poi="天安门",
            source="gaode",
        )

    monkeypatch.setattr(geocode_service, "reverse_geocode_gaode", fake_gaode)
    monkeypatch.setattr(
        geocode_service,
        "reverse_geocode_offline",
        lambda lat, lon: GeoLocation(country="中国", country_code="CN", city="Beijing", source="offline"),
    )

    loc, called = asyncio.run(
        get_location(39.9042, 116.4074, gaode_api_key="k", trip_type="domestic")
    )
    assert calls == [(39.9042, 116.4074)]
    assert called is True
    assert loc.source == "gaode"
    assert loc.country_code == "CN"
    assert loc.poi == "天安门"
    assert is_china_anomaly(39.9042, 116.4074, "domestic") is False


def test_anomaly_domestic_foreign_and_abroad_china():
    assert is_china_anomaly(37.57, 126.98, "domestic") is True
    assert is_china_anomaly(39.9042, 116.4074, "abroad") is True
    assert is_china_anomaly(39.9042, 116.4074, "mixed") is False


def test_missing_boundary_falls_back_to_bbox(monkeypatch):
    monkeypatch.setattr(geocode_service, "_CHINA_RINGS", [])
    assert is_in_china(39.9, 116.4) is True
    assert is_in_china(37.57, 126.98) is True  # bbox 兜底会包含首尔
