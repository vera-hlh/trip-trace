"""M4.3：持久缓存与 force_repoi 去重"""
import asyncio

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.scan import GeocodeRequest, geocode_scanned_files
from app.core.database import Base
from app.models import archive_log, archive_plan, cache, file, trip, trip_record  # noqa: F401
from app.models.cache import GeocodeCache
from app.models.file import MediaFile
from app.services import geocode_service
from app.services.geocode_cache import (
    cache_is_usable,
    load_cache,
    location_from_row,
    store_location,
)
from app.services.geocode_service import GeoLocation


async def make_db(tmp_path, name):
    db_path = (tmp_path / name).as_posix()
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)()


def test_cache_roundtrip_and_no_downgrade(tmp_path):
    async def run():
        engine, db = await make_db(tmp_path, "cache.sqlite")
        try:
            cache_map = await load_cache(db)
            loc = GeoLocation(
                country="中国",
                country_code="CN",
                province="云南省",
                city="昆明市",
                district="石林县",
                township="石林镇",
                poi="石林风景区",
                poi_type="风景名胜",
                source="gaode",
            )
            store_location(db, cache_map, 25.038912, 102.718356, loc)
            await db.commit()

            cache_map = await load_cache(db)
            row = next(iter(cache_map.values()))
            assert row.lat_key == 25.039
            assert row.lon_key == 102.718
            assert location_from_row(row).poi == "石林风景区"

            # 同一网格更新，不应新增行；离线结果不能降级高德结果
            store_location(
                db,
                cache_map,
                25.03899,
                102.71835,
                GeoLocation(country="中国", city="昆明", source="offline"),
            )
            await db.commit()
            count = (await db.execute(select(func.count(GeocodeCache.id)))).scalar()
            assert count == 1
            row = (await db.execute(select(GeocodeCache))).scalar_one()
            assert row.source == "gaode"
            assert row.poi == "石林风景区"
        finally:
            await db.close()
            await engine.dispose()

    asyncio.run(run())


def test_cache_usable_policy():
    offline = GeocodeCache(source="offline")
    gaode = GeocodeCache(source="gaode", poi="天安门")

    assert cache_is_usable(None, 39.9, 116.4, "k", "domestic") is False
    assert cache_is_usable(offline, 39.9, 116.4, "", "domestic") is True
    assert cache_is_usable(offline, 39.9, 116.4, "k", "domestic") is False
    assert cache_is_usable(offline, 37.57, 126.98, "k", "mixed") is True
    assert cache_is_usable(gaode, 39.9, 116.4, "k", "abroad") is True


def test_force_repoi_dedupes_by_grid(tmp_path, monkeypatch):
    async def run():
        engine, db = await make_db(tmp_path, "force.sqlite")
        try:
            db.add_all([
                MediaFile(
                    original_path="C:/in/a.jpg",
                    current_path="C:/in/a.jpg",
                    file_name="a.jpg",
                    file_type="photo",
                    datetime_original="2025-09-10T09:00:00",
                    latitude=25.03891,
                    longitude=102.71831,
                    has_gps=True,
                    city="昆明市",
                    geocode_source="gaode",
                ),
                MediaFile(
                    original_path="C:/in/b.jpg",
                    current_path="C:/in/b.jpg",
                    file_name="b.jpg",
                    file_type="photo",
                    datetime_original="2025-09-10T09:05:00",
                    latitude=25.03892,
                    longitude=102.71832,
                    has_gps=True,
                    city="昆明市",
                    geocode_source="gaode",
                ),
            ])
            await db.commit()

            calls = []

            async def fake_gaode(lat, lon, key):
                calls.append((lat, lon))
                return GeoLocation(
                    country="中国",
                    country_code="CN",
                    province="云南省",
                    city="昆明市",
                    poi="石林风景区",
                    poi_type="风景名胜",
                    source="gaode",
                )

            monkeypatch.setattr(geocode_service, "reverse_geocode_gaode", fake_gaode)
            monkeypatch.setattr("app.core.config.settings.gaode_api_key", "test-key")

            resp = await geocode_scanned_files(
                GeocodeRequest(force_repoi=True, trip_type="domestic"), db
            )
            assert len(calls) == 1
            assert resp["api_calls"] == 1
            assert resp["updated"] == 2
            assert resp["estimated_calls"] == 1

            files = (await db.execute(select(MediaFile))).scalars().all()
            assert all(f.poi == "石林风景区" for f in files)
            assert all(f.poi_type == "风景名胜" for f in files)

            cache_row = (await db.execute(select(GeocodeCache))).scalar_one()
            assert cache_row.source == "gaode"
            assert cache_row.poi == "石林风景区"
        finally:
            await db.close()
            await engine.dispose()

    asyncio.run(run())
