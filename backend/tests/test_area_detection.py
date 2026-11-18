"""景区候选：AOI 与父级 POI 链（Phase 1）"""
import asyncio
import json

from app.services import geocode_service
from app.services.geocode_service import (
    GeoLocation,
    PoiClusterState,
    _pick_aoi_candidate,
    _resolve_amap_parent,
    get_location,
)


def test_pick_aoi_candidate_prefers_scenic():
    aois = [
        {"name": "时代购物广场", "type": "060101", "distance": "3"},
        {"name": "三峡大坝旅游区", "type": "110202", "distance": "47"},
    ]
    candidate = _pick_aoi_candidate(aois)
    assert candidate is not None
    assert candidate["name"] == "三峡大坝旅游区"
    assert candidate["source"] == "amap_aoi"
    assert candidate["confidence"] == 0.9


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _FakeClient:
    async def get(self, url, params=None):
        poi_id = (params or {}).get("id")
        if poi_id == "child":
            return _FakeResponse({"pois": [{
                "name": "185园区-观景台",
                "type": "风景名胜;风景名胜相关;旅游景点",
                "parent": "middle",
            }]})
        if poi_id == "middle":
            return _FakeResponse({"pois": [{
                "name": "坛子岭风景区",
                "type": "风景名胜;风景名胜;国家级景点",
                "parent": "top",
            }]})
        if poi_id == "top":
            return _FakeResponse({"pois": [{
                "name": "三峡大坝旅游区",
                "type": "110202",
                "parent": "",
            }]})
        return _FakeResponse({"pois": []})


def test_resolve_parent_chain_picks_highest_scenic_area():
    geocode_service._AMAP_PARENT_CACHE.clear()
    candidate = asyncio.run(
        _resolve_amap_parent(_FakeClient(), "key", "middle")
    )
    assert candidate is not None
    assert candidate["name"] == "三峡大坝旅游区"
    assert candidate["source"] == "amap_parent"
    assert candidate["confidence"] >= 0.85


def test_cluster_preserves_area_fields():
    cluster = PoiClusterState(
        poi_name="坛子岭",
        city="宜昌市",
        center_lat=30.83,
        center_lon=111.01,
        province="湖北省",
        area_name="三峡大坝旅游区",
        area_source="amap_aoi",
        area_confidence=0.9,
        area_candidates=[{"name": "三峡大坝旅游区", "source": "amap_aoi"}],
        source="gaode",
    )
    loc, called = asyncio.run(
        get_location(lat=30.83, lon=111.01, poi_clusters=[cluster])
    )
    assert called is False
    assert loc.area_name == "三峡大坝旅游区"
    assert loc.area_source == "amap_aoi"
    assert loc.area_confidence == 0.9
    assert loc.area_candidates[0]["name"] == "三峡大坝旅游区"


def test_cache_area_fields_roundtrip(tmp_path):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.core.database import Base
    from app.models import archive_log, archive_plan, cache, file, trip, trip_record  # noqa: F401
    from app.models.cache import GeocodeCache
    from app.services.geocode_cache import load_cache, location_from_row, store_location

    async def run():
        db_path = (tmp_path / "area.sqlite").as_posix()
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as db:
            cache_map = await load_cache(db)
            store_location(
                db,
                cache_map,
                30.83,
                111.01,
                GeoLocation(
                    country="中国",
                    city="宜昌市",
                    area_name="三峡大坝旅游区",
                    area_source="amap_aoi",
                    area_confidence=0.9,
                    area_candidates=[{"name": "三峡大坝旅游区", "source": "amap_aoi"}],
                    source="gaode",
                ),
            )
            await db.commit()
            cache_map = await load_cache(db)
            row = next(iter(cache_map.values()))
            loc = location_from_row(row)
            assert row.area_name == "三峡大坝旅游区"
            assert loc.area_candidates[0]["name"] == "三峡大坝旅游区"
        await engine.dispose()

    asyncio.run(run())


def test_area_group_update_only_touches_matching_group(tmp_path):
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.api.scan import AreaGroupUpdate, update_area_group
    from app.core.database import Base
    from app.models import archive_log, archive_plan, cache, file, trip, trip_record  # noqa: F401
    from app.models.file import MediaFile

    async def run():
        db_path = (tmp_path / "area_update.sqlite").as_posix()
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as db:
            for i in range(2):
                db.add(MediaFile(
                    original_path=f"C:/in/{i}.jpg",
                    current_path=f"C:/in/{i}.jpg",
                    file_name=f"{i}.jpg",
                    file_type="photo",
                    province="湖北省",
                    city="宜昌市",
                    area_name="三峡大坝旅游区",
                    area_source="amap_aoi",
                    area_confidence=0.9,
                    poi="坛子岭",
                ))
            db.add(MediaFile(
                original_path="C:/in/other.jpg",
                current_path="C:/in/other.jpg",
                file_name="other.jpg",
                file_type="photo",
                province="湖北省",
                city="宜昌市",
                area_name="三峡人家风景区",
                area_source="amap_aoi",
                poi="龙进溪",
            ))
            await db.commit()

            resp = await update_area_group(
                AreaGroupUpdate(
                    province="湖北省",
                    city="宜昌市",
                    old_area="三峡大坝旅游区",
                    old_poi="坛子岭",
                    new_area="三峡大坝景区",
                ),
                db,
            )
            assert resp["updated"] == 2

            rows = (await db.execute(select(MediaFile).order_by(MediaFile.file_name))).scalars().all()
            changed = [r for r in rows if r.file_name in ("0.jpg", "1.jpg")]
            assert all(r.area_name == "三峡大坝景区" for r in changed)
            assert all(r.area_source == "manual" for r in changed)
            other = next(r for r in rows if r.file_name == "other.jpg")
            assert other.area_name == "三峡人家风景区"
        await engine.dispose()

    asyncio.run(run())
