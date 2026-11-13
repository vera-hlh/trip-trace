"""Overpass 附近景点查询测试（M4.5）"""
import asyncio

from app.models.cache import GeocodeCache
from app.services import geocode_service
from app.services.geocode_cache import cache_is_usable
from app.services.geocode_service import (
    GeoLocation,
    _parse_overpass_elements,
    get_location,
)


def test_parse_overpass_prefers_named_travel_poi():
    elements = [
        {
            "type": "node", "lat": 37.5665, "lon": 126.9780,
            "tags": {"amenity": "cafe", "name": "Happy Cafe"},
        },
        {
            "type": "node", "lat": 37.5670, "lon": 126.9780,
            "tags": {"tourism": "attraction", "name:zh": "景福宫"},
        },
        {
            "type": "way", "center": {"lat": 37.5700, "lon": 126.9800},
            "tags": {"leisure": "park", "name": "City Park"},
        },
    ]
    assert _parse_overpass_elements(elements, 37.5665, 126.9780) == ("景福宫", "风景名胜")


def test_parse_overpass_ignores_unnamed_and_hotel():
    elements = [
        {"type": "node", "lat": 37.56, "lon": 126.97, "tags": {"tourism": "hotel", "name": "Hotel"}},
        {"type": "node", "lat": 37.56, "lon": 126.97, "tags": {"tourism": "museum"}},
    ]
    assert _parse_overpass_elements(elements, 37.5665, 126.9780) is None


def test_get_location_fills_poi_from_overpass(monkeypatch):
    overpass_calls = []

    async def fake_nominatim(lat, lon, user_agent, **kwargs):
        return GeoLocation(
            country="韩国", country_code="KR", city="首尔", source="nominatim"
        )

    async def fake_overpass(lat, lon, user_agent, **kwargs):
        overpass_calls.append((lat, lon))
        return "景福宫", "风景名胜"

    monkeypatch.setattr(geocode_service, "reverse_geocode_nominatim", fake_nominatim)
    monkeypatch.setattr(geocode_service, "find_nearby_travel_poi", fake_overpass)
    monkeypatch.setattr(
        geocode_service,
        "reverse_geocode_offline",
        lambda lat, lon: GeoLocation(country="韩国", country_code="KR", city="Seoul", source="offline"),
    )

    loc, called = asyncio.run(
        get_location(
            37.57,
            126.98,
            gaode_api_key="k",
            trip_type="abroad",
            nominatim_enabled=True,
            overpass_enabled=True,
        )
    )
    assert len(overpass_calls) == 1
    assert called is True
    assert loc.city == "首尔"
    assert loc.poi == "景福宫"
    assert loc.poi_type == "风景名胜"


def test_cache_understands_overpass_source():
    overpass = GeocodeCache(source="overpass", poi="景福宫")
    offline = GeocodeCache(source="offline")

    assert cache_is_usable(overpass, 37.57, 126.98, "k", "abroad", False, True) is True
    assert cache_is_usable(offline, 37.57, 126.98, "k", "abroad", False, True) is False
