"""归档方案模型：注册与基本读写测试"""
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models import archive_plan, file, trip  # noqa: F401  注册表
from app.models.archive_plan import ArchivePlan, PlanFile, PlanTrip


def test_plan_tables_registered():
    assert {"archive_plans", "plan_trips", "plan_files"} <= set(Base.metadata.tables)


def test_plan_roundtrip(tmp_path):
    async def run():
        db_path = (tmp_path / "plan.sqlite").as_posix()
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with session_factory() as db:
            plan = ArchivePlan(
                source_folder="C:/in",
                output_folder="C:/out",
                created_at="2026-11-13T00:00:00",
            )
            db.add(plan)
            await db.flush()

            big = PlanTrip(
                plan_id=plan.id,
                kind="big",
                folder_name="2025_云南_11天_0910-0920",
                display_name="云南之旅",
                start_date="2025-09-10",
                end_date="2025-09-20",
                sort_order=0,
            )
            db.add(big)
            await db.flush()

            sub = PlanTrip(
                plan_id=plan.id,
                parent_id=big.id,
                kind="sub",
                folder_name="01_昆明_0910-0913",
                display_name="昆明",
                start_date="2025-09-10",
                end_date="2025-09-13",
                sequence_num=1,
                location_label="昆明",
                sort_order=0,
            )
            db.add(sub)
            await db.flush()

            item = PlanFile(
                plan_id=plan.id,
                trip_id=sub.id,
                media_file_id=None,
                target_rel_path="2025_云南_11天_0910-0920/01_昆明_0910-0913/IMG_001.jpg",
            )
            db.add(item)
            await db.commit()
            plan_id = plan.id

        async with session_factory() as db:
            got = (
                await db.execute(select(ArchivePlan).where(ArchivePlan.id == plan_id))
            ).scalar_one()
            assert got.status == "draft"
            assert got.plan_version == 1

            trips = (
                await db.execute(select(PlanTrip).where(PlanTrip.plan_id == plan_id))
            ).scalars().all()
            assert len(trips) == 2
            assert {t.kind for t in trips} == {"big", "sub"}

            files = (
                await db.execute(select(PlanFile).where(PlanFile.plan_id == plan_id))
            ).scalars().all()
            assert len(files) == 1
            assert files[0].status == "pending"
            assert files[0].target_rel_path.endswith("IMG_001.jpg")

        await engine.dispose()

    asyncio.run(run())
