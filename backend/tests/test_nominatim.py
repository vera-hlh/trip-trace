"""境外 Nominatim 接入测试（M4.4）"""
import asyncio

from app.models.cache import GeocodeCache
from app.services import geocode_service
from app.services.geocode_cache import cache_is_usable
from app.services.geocode_service import (
    GeoLocation,
    _parse_nominatim_payload,
    get_location,
)


def test_parse_nominatim_payload():
    payload = {
        "name": "Gyeongbokgung Palace",
        "type": "attraction",
        "address": {
            "country": "South Korea",
            "country_code": "kr",
            "state": "Seoul",
            "city": "Seoul",
            "suburb": "Jongno-gu",
        },
        "namedetails": {"name:zh": "景福宫"},
        "display_name": "景福宫, Seoul, South Korea",
    }
    loc = _parse_nominatim_payload(payload)
    assert loc is not None
    assert loc.country == "South Korea"
    assert loc.country_code == "KR"
    assert loc.city == "Seoul"
    assert loc.district == "Jongno-gu"
    assert loc.poi == "景福宫"
    assert loc.source == "nominatim"


def test_parse_nominatim_ignores_cafe_as_poi():
    payload = {
        "name": "Happy Plus Cafe",
        "category": "amenity",
        "type": "cafe",
        "address": {
            "country": "South Korea",
            "country_code": "kr",
            "city": "Seoul",
        },
    }
    loc = _parse_nominatim_payload(payload)
    assert loc is not None
    assert loc.city == "Seoul"
    assert loc.poi == ""
    assert loc.poi_type == ""


def test_get_location_uses_nominatim_abroad(monkeypatch):
    calls = []

    async def fake_nominatim(lat, lon, user_agent, **kwargs):
        calls.append((lat, lon, user_agent))
        return GeoLocation(
            country="韩国",
            country_code="KR",
            province="首尔特别市",
            city="首尔",
            district="钟路区",
            poi="景福宫",
            source="nominatim",
        )

    monkeypatch.setattr(geocode_service, "reverse_geocode_nominatim", fake_nominatim)
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
            nominatim_user_agent="TripTrace/0.1 (test@example.com)",
        )
    )
    assert len(calls) == 1
    assert calls[0][2] == "TripTrace/0.1 (test@example.com)"
    assert called is True
    assert loc.source == "nominatim"
    assert loc.poi == "景福宫"


def test_domestic_does_not_use_nominatim(monkeypatch):
    calls = []

    async def fake_nominatim(*args, **kwargs):
        calls.append(args)
        return GeoLocation(city="Seoul", source="nominatim")

    monkeypatch.setattr(geocode_service, "reverse_geocode_nominatim", fake_nominatim)
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
            trip_type="domestic",
            nominatim_enabled=True,
        )
    )
    assert calls == []
    assert called is False
    assert loc.source == "offline"


def test_cache_understands_nominatim_source():
    nominatim = GeocodeCache(source="nominatim", poi="景福宫")
    offline = GeocodeCache(source="offline")

    assert cache_is_usable(nominatim, 37.57, 126.98, "k", "abroad", True) is True
    assert cache_is_usable(offline, 37.57, 126.98, "k", "abroad", True) is False
    assert cache_is_usable(offline, 37.57, 126.98, "k", "domestic", True) is True
