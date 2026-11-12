"""M4.1：中国国界多边形与 trip_type 策略"""
import pytest

from app.services import geocode_service
from app.services.geocode_service import GeoLocation, get_location, is_in_china


def test_china_polygon_known_points():
    assert is_in_china(39.9042, 116.4074) is True      # 北京
    assert is_in_china(52.97, 122.53) is True          # 漠河
    assert is_in_china(31.23, 121.47) is True          # 上海
    assert is_in_china(29.65, 91.14) is True           # 拉萨
    assert is_in_china(37.57, 126.98) is False         # 首尔
    assert is_in_china(21.03, 105.85) is False         # 河内
    assert is_in_china(47.89, 106.91) is False         # 乌兰巴托
    assert is_in_china(43.12, 131.89) is False         # 海参崴


def test_trip_type_abroad_forces_offline(monkeypatch):
    calls = []

    async def fake_gaode(lat, lon, key):
        calls.append((lat, lon))
        return GeoLocation(province="北京市", city="北京市", poi="天安门", source="gaode")

    monkeypatch.setattr(geocode_service, "reverse_geocode_gaode", fake_gaode)
    monkeypatch.setattr(
        geocode_service,
        "reverse_geocode_offline",
        lambda lat, lon: GeoLocation(country="中国", country_code="CN", city="北京", source="offline"),
    )

    import asyncio

    loc, called = asyncio.run(
        get_location(39.9042, 116.4074, gaode_api_key="k", trip_type="abroad")
    )
    assert calls == []
    assert called is False
    assert loc.source == "offline"


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

    import asyncio

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

    import asyncio

    loc, called = asyncio.run(
        get_location(39.9042, 116.4074, gaode_api_key="k", trip_type="domestic")
    )
    assert calls == [(39.9042, 116.4074)]
    assert called is True
    assert loc.source == "gaode"
    assert loc.country_code == "CN"
    assert loc.poi == "天安门"


def test_missing_boundary_falls_back_to_bbox(monkeypatch):
    monkeypatch.setattr(geocode_service, "_CHINA_RINGS", [])
    assert is_in_china(39.9, 116.4) is True
    assert is_in_china(37.57, 126.98) is True  # bbox 兜底会包含首尔
