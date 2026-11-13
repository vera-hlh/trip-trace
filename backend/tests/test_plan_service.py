"""归档方案生成/读取测试（M2.2）"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models import archive_plan, file, trip  # noqa: F401  注册表
from app.models.archive_plan import ArchivePlan, PlanFile, PlanTrip
from app.api.plans import ArchiveOptions
from app.api.plans import build_plan_from_files, get_plan


def make_file(file_id: int, name: str, dt: str, city: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=file_id,
        original_path=f"C:/in/{name}",
        file_name=name,
        file_type="photo",
        datetime_original=dt,
        latitude=25.0,
        longitude=102.0,
        country="中国",
        province="",
        city=city,
        district=None,
        township=None,
        poi=None,
        has_gps=True,
        needs_review=False,
    )


def test_build_and_read_plan(tmp_path):
    async def run():
        db_path = (tmp_path / "plan_service.sqlite").as_posix()
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        db_files = [
            make_file(1, "k1.jpg", "2025-09-10T09:00:00", "昆明"),
            make_file(2, "k2.jpg", "2025-09-10T11:00:00", "昆明"),
            make_file(3, "d1.jpg", "2025-09-10T14:00:00", "大理"),
            make_file(4, "d2.jpg", "2025-09-10T16:00:00", "大理"),
        ]

        async with session_factory() as db:
            plan, big_count, sub_count = await build_plan_from_files(
                db,
                db_files,
                "C:/in",
                "C:/out",
                ArchiveOptions(gaode_api_key="should-not-be-stored"),
            )
            assert isinstance(plan, ArchivePlan)
            assert plan.status == "draft"
            assert plan.plan_version == 1
            assert len(plan.source_snapshot) == 64
            assert big_count == 1
            assert sub_count == 2

            trips = (
                await db.execute(select(PlanTrip).where(PlanTrip.plan_id == plan.id))
            ).scalars().all()
            assert len(trips) == 3
            assert {t.kind for t in trips} == {"big", "sub"}

            files = (
                await db.execute(select(PlanFile).where(PlanFile.plan_id == plan.id))
            ).scalars().all()
            assert len(files) == 4
            assert all(f.status == "pending" for f in files)
            assert all(f.target_rel_path.endswith(".jpg") for f in files)

            resp = await get_plan(plan.id, db)
            data = resp["data"]
            assert data["plan"]["id"] == plan.id
            assert "should-not-be-stored" not in (data["plan"]["options"] or {}).values()
            assert len(data["trips_structure"]) == 1
            big = data["trips_structure"][0]
            assert big["total_files"] == 4
            assert len(big["sub_trips"]) == 2
            assert len(data["files"]) == 4

            with pytest.raises(HTTPException) as exc:
                await get_plan(99999, db)
            assert exc.value.status_code == 404

        await engine.dispose()

    asyncio.run(run())
