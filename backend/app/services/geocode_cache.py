"""逆地理编码持久缓存（M4.3）

以 (lat, lon) 3 位小数网格为 key，缓存离线/高德结果，避免重复请求。
"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cache import GeocodeCache
from app.services.geocode_service import (
    GeoLocation,
    allow_geocode_online,
    is_in_china,
    make_cache_key,
)

ONLINE_SOURCES = {"gaode", "nominatim", "overpass"}


async def load_cache(db: AsyncSession) -> dict[tuple[float, float], GeocodeCache]:
    rows = (await db.execute(select(GeocodeCache))).scalars().all()
    return {(row.lat_key, row.lon_key): row for row in rows}


def location_from_row(row: GeocodeCache) -> GeoLocation:
    return GeoLocation(
        country=row.country or "",
        country_code=row.country_code or "",
        province=row.province or "",
        city=row.city or "",
        district=row.district or "",
        township=row.township or "",
        poi=row.poi or "",
        poi_type=row.poi_type or "",
        source=row.source or "offline",
    )


def cache_is_usable(
    row: GeocodeCache | None,
    lat: float,
    lon: float,
    gaode_api_key: str,
    trip_type: str,
    nominatim_enabled: bool = False,
    overpass_enabled: bool = False,
) -> bool:
    if row is None:
        return False
    if row.source in ONLINE_SOURCES:
        return True
    # 离线缓存：没有任何在线 provider，或该坐标本来就不允许在线查询时，可直接复用
    if not gaode_api_key and not nominatim_enabled and not overpass_enabled:
        return True
    if allow_geocode_online(lat, lon, trip_type):
        return False
    if (
        (nominatim_enabled or overpass_enabled)
        and trip_type in ("abroad", "mixed")
        and not is_in_china(lat, lon)
    ):
        return False
    return True


def store_location(
    db: AsyncSession,
    cache_map: dict[tuple[float, float], GeocodeCache],
    lat: float,
    lon: float,
    location: GeoLocation,
) -> None:
    key = make_cache_key(lat, lon)
    row = cache_map.get(key)
    if row is None:
        row = GeocodeCache(lat_key=key[0], lon_key=key[1])
        db.add(row)
        cache_map[key] = row

    # 已有在线结果时，不让后续离线结果把它降级
    if row.source in ONLINE_SOURCES and location.source not in ONLINE_SOURCES:
        return

    row.country = location.country or row.country
    row.country_code = location.country_code or row.country_code
    row.province = location.province or row.province
    row.city = location.city or row.city
    row.district = location.district or row.district
    row.township = location.township or row.township
    row.poi = location.poi or row.poi
    row.poi_type = location.poi_type or row.poi_type
    row.source = location.source or row.source or "offline"
    row.cached_at = datetime.now().isoformat(timespec="seconds")
