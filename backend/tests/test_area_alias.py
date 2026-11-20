"""景区别名与归一化测试。"""
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.scan import AreaMergeRequest, merge_area_names
from app.core.database import Base
from app.models import area_alias, archive_log, archive_plan, cache, file, trip, trip_record  # noqa: F401
from app.models.area_alias import AreaAlias
from app.models.file import MediaFile
from app.services.area_alias_service import load_aliases, resolve_area_alias


def test_alias_resolution_chain():
    aliases = {
        ("宜昌市", "坛子岭风景区"): "三峡大坝旅游区",
        ("宜昌市", "三峡大坝景区"): "三峡大坝旅游区",
    }
    assert resolve_area_alias(aliases, "宜昌市", "坛子岭风景区") == "三峡大坝旅游区"
    assert resolve_area_alias(aliases, "宜昌市", "三峡人家风景区") == "三峡人家风景区"
    # 不同城市不串用
    assert resolve_area_alias(aliases, "衡阳市", "坛子岭风景区") == "坛子岭风景区"


def test_area_merge_updates_files_and_alias(tmp_path):
    async def run():
        db_path = (tmp_path / "aliases.sqlite").as_posix()
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as db:
            db.add_all([
                MediaFile(
                    original_path="C:/in/a.jpg", current_path="C:/in/a.jpg",
                    file_name="a.jpg", file_type="photo",
                    city="宜昌市", area_name="坛子岭风景区",
                ),
                MediaFile(
                    original_path="C:/in/b.jpg", current_path="C:/in/b.jpg",
                    file_name="b.jpg", file_type="photo",
                    city="宜昌市", area_name="三峡大坝旅游区",
                ),
                MediaFile(
                    original_path="C:/in/c.jpg", current_path="C:/in/c.jpg",
                    file_name="c.jpg", file_type="photo",
                    city="衡阳市", area_name="坛子岭风景区",
                ),
            ])
            await db.commit()

            resp = await merge_area_names(
                AreaMergeRequest(
                    city="宜昌市",
                    source_names=["坛子岭风景区", "三峡大坝旅游区"],
                    canonical_name="三峡大坝旅游区",
                ),
                db,
            )
            assert resp["success"] is True
            assert resp["canonical_name"] == "三峡大坝旅游区"
            assert resp["updated"] == 1

            rows = (await db.execute(select(MediaFile).order_by(MediaFile.file_name))).scalars().all()
            assert rows[0].area_name == "三峡大坝旅游区"
            assert rows[0].area_source == "manual"
            assert rows[1].area_name == "三峡大坝旅游区"
            # 其他城市不受影响
            assert rows[2].area_name == "坛子岭风景区"

            alias = (await db.execute(select(AreaAlias))).scalar_one()
            assert alias.alias_name == "坛子岭风景区"
            assert alias.canonical_name == "三峡大坝旅游区"

            aliases = await load_aliases(db)
            assert resolve_area_alias(aliases, "宜昌市", "坛子岭风景区") == "三峡大坝旅游区"
        await engine.dispose()

    asyncio.run(run())
