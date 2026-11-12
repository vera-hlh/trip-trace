"""归档方案执行测试（M2.4）：只消费 plan，不再重算"""
import asyncio
import os

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.archive import ArchiveOptions
from app.api.plans import (
    TripMerge,
    PlanPatchRequest,
    build_plan_from_files,
    execute_plan,
    get_plan,
    patch_plan,
)
from app.core.database import Base, get_db
from app.main import app
from app.models import archive_log, archive_plan, file, trip, trip_record  # noqa: F401
from app.models.archive_log import ArchiveLog
from app.models.archive_plan import ArchivePlan, PlanFile, PlanTrip
from app.models.file import MediaFile
from app.models.trip_record import TripRecord
from app.services.plan_executor import run_plan, source_snapshot


async def make_db(tmp_path):
    db_path = (tmp_path / "execute.sqlite").as_posix()
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)()


async def make_media(db, input_dir, name, dt, city):
    path = input_dir / name
    path.write_bytes(b"fake-image-" + name.encode())
    row = MediaFile(
        original_path=str(path),
        current_path=str(path),
        file_name=name,
        file_type="photo",
        datetime_original=dt,
        latitude=25.0,
        longitude=102.0,
        country="中国",
        province="",
        city=city,
        has_gps=True,
        needs_review=False,
        geocode_source="offline",
    )
    db.add(row)
    return row


def test_execute_plan_honors_merge(tmp_path):
    async def run():
        engine, db = await make_db(tmp_path)
        try:
            input_dir = tmp_path / "input"
            output_dir = tmp_path / "output"
            input_dir.mkdir()

            rows = [
                await make_media(db, input_dir, "k1.jpg", "2025-09-10T09:00:00", "昆明"),
                await make_media(db, input_dir, "k2.jpg", "2025-09-10T11:00:00", "昆明"),
                await make_media(db, input_dir, "d1.jpg", "2025-09-10T14:00:00", "大理"),
                await make_media(db, input_dir, "d2.jpg", "2025-09-10T16:00:00", "大理"),
            ]
            await db.commit()

            plan, big_count, sub_count = await build_plan_from_files(
                db, rows, str(input_dir), str(output_dir), ArchiveOptions()
            )
            assert (big_count, sub_count) == (1, 2)

            data = (await get_plan(plan.id, db))["data"]
            big = data["trips_structure"][0]
            sub1, sub2 = big["sub_trips"]

            # 合并两个子行程
            await patch_plan(
                plan.id,
                PlanPatchRequest(
                    plan_version=1,
                    merges=[TripMerge(source_ids=[sub2["id"]], target_id=sub1["id"])],
                ),
                db,
            )

            plan = (
                await db.execute(select(ArchivePlan).where(ArchivePlan.id == plan.id))
            ).scalar_one()
            media = (
                await db.execute(select(MediaFile).order_by(MediaFile.id))
            ).scalars().all()
            assert source_snapshot(media) == plan.source_snapshot

            events = []
            async for event in run_plan(db, plan, media, False, ""):
                events.append(event)

            complete = events[-1]
            assert complete["type"] == "complete"
            assert complete["copied"] == 4
            assert complete["errors"] == 0

            # 输出结构：大行程/唯一子行程/4 个文件 + trip_log.md
            big_dirs = [p for p in output_dir.iterdir() if p.is_dir()]
            assert len(big_dirs) == 1
            sub_dirs = [p for p in big_dirs[0].iterdir() if p.is_dir()]
            assert len(sub_dirs) == 1
            files = sorted(p.name for p in sub_dirs[0].iterdir() if p.is_file())
            assert files == ["d1.jpg", "d2.jpg", "k1.jpg", "k2.jpg"]
            assert (big_dirs[0] / "trip_log.md").exists()

            # 方案/文件/日志/记录
            await db.refresh(plan)
            assert plan.status == "executed"
            plan_files = (
                await db.execute(select(PlanFile).where(PlanFile.plan_id == plan.id))
            ).scalars().all()
            assert all(pf.status == "copied" for pf in plan_files)

            logs = (await db.execute(select(ArchiveLog))).scalars().all()
            assert len(logs) == 1
            assert logs[0].copied_count == 4

            records = (await db.execute(select(TripRecord))).scalars().all()
            assert len(records) == 1
            assert records[0].sub_trip_count == 1
            assert records[0].total_files == 4

            assert all(m.current_path and os.path.exists(m.current_path) for m in media)
        finally:
            await db.close()
            await engine.dispose()

    asyncio.run(run())


def test_execute_rejects_stale_snapshot(tmp_path):
    async def run():
        engine, db = await make_db(tmp_path)
        try:
            input_dir = tmp_path / "input"
            input_dir.mkdir()
            row = await make_media(db, input_dir, "a.jpg", "2025-09-10T09:00:00", "昆明")
            await db.commit()

            plan, _, _ = await build_plan_from_files(
                db, [row], str(input_dir), str(tmp_path / "output"), ArchiveOptions()
            )

            # 修改源文件 mtime，使快照失效
            os.utime(row.original_path, (os.stat(row.original_path).st_atime + 10,
                                         os.stat(row.original_path).st_mtime + 10))

            with pytest.raises(HTTPException) as exc:
                await execute_plan(plan.id, None, db)
            assert exc.value.status_code == 409
        finally:
            await db.close()
            await engine.dispose()

    asyncio.run(run())


def test_execute_endpoint_sse(tmp_path):
    async def run():
        engine, db = await make_db(tmp_path)
        try:
            input_dir = tmp_path / "input"
            input_dir.mkdir()
            row = await make_media(db, input_dir, "sse.jpg", "2025-09-10T09:00:00", "昆明")
            await db.commit()

            plan, _, _ = await build_plan_from_files(
                db, [row], str(input_dir), str(tmp_path / "output"), ArchiveOptions()
            )

            async def override_get_db():
                yield db

            app.dependency_overrides[get_db] = override_get_db
            try:
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    resp = await client.post(
                        f"/api/archive/plans/{plan.id}/execute", json={}
                    )
                assert resp.status_code == 200
                assert '"type": "complete"' in resp.text
            finally:
                app.dependency_overrides.clear()

            await db.refresh(plan)
            assert plan.status == "executed"
        finally:
            await db.close()
            await engine.dispose()

    asyncio.run(run())
