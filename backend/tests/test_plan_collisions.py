"""M3.1：同名冲突与复制校验"""
import asyncio
import os

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.plans import ArchiveOptions
from app.api.plans import build_plan_from_files
from app.core.database import Base
from app.models import archive_log, archive_plan, file, trip, trip_record  # noqa: F401
from app.models.archive_plan import PlanFile
from app.models.file import MediaFile
from app.services import plan_executor
from app.services.plan_executor import run_plan


async def make_db(tmp_path):
    db_path = (tmp_path / "collision.sqlite").as_posix()
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)()


async def add_media(db, path, dt, city="昆明"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"content-" + path.name.encode())
    row = MediaFile(
        original_path=str(path),
        current_path=str(path),
        file_name=path.name,
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


def test_same_filename_keeps_source_subdirs(tmp_path):
    async def run():
        engine, db = await make_db(tmp_path)
        try:
            root = tmp_path / "input"
            a = await add_media(db, root / "phoneA" / "IMG_0001.jpg", "2025-09-10T09:00:00")
            b = await add_media(db, root / "phoneB" / "IMG_0001.jpg", "2025-09-10T11:00:00")
            await db.commit()

            plan, _, _ = await build_plan_from_files(
                db, [a, b], str(root), str(tmp_path / "out"), ArchiveOptions()
            )
            files = (
                await db.execute(select(PlanFile).where(PlanFile.plan_id == plan.id))
            ).scalars().all()
            paths = [f.target_rel_path for f in files]
            assert len(paths) == 2
            assert paths[0] != paths[1]
            assert "phoneA" in paths[0].replace("\\", "/")
            assert "phoneB" in paths[1].replace("\\", "/")

            media = (
                await db.execute(select(MediaFile).order_by(MediaFile.id))
            ).scalars().all()
            events = []
            async for event in run_plan(db, plan, media, False, ""):
                events.append(event)
            assert events[-1]["copied"] == 2
            assert events[-1]["errors"] == 0

            for rel in paths:
                assert (tmp_path / "out" / rel).exists()
        finally:
            await db.close()
            await engine.dispose()

    asyncio.run(run())


def test_existing_target_with_different_content_is_error(tmp_path):
    async def run():
        engine, db = await make_db(tmp_path)
        try:
            root = tmp_path / "input"
            out = tmp_path / "out"
            row = await add_media(db, root / "IMG_0001.jpg", "2025-09-10T09:00:00")
            await db.commit()

            plan, _, _ = await build_plan_from_files(
                db, [row], str(root), str(out), ArchiveOptions()
            )
            pf = (
                await db.execute(select(PlanFile).where(PlanFile.plan_id == plan.id))
            ).scalar_one()
            target = out / pf.target_rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"different-content")

            media = (
                await db.execute(select(MediaFile).where(MediaFile.id == row.id))
            ).scalar_one()
            events = []
            async for event in run_plan(db, plan, [media], False, ""):
                events.append(event)
            assert events[-1]["errors"] == 1
            assert events[-1]["copied"] == 0
            assert target.read_bytes() == b"different-content"
            await db.refresh(pf)
            assert pf.status == "failed"
        finally:
            await db.close()
            await engine.dispose()

    asyncio.run(run())


def test_copy_verification_removes_bad_target(tmp_path, monkeypatch):
    async def run():
        engine, db = await make_db(tmp_path)
        try:
            root = tmp_path / "input"
            out = tmp_path / "out"
            row = await add_media(db, root / "IMG_0001.jpg", "2025-09-10T09:00:00")
            await db.commit()

            plan, _, _ = await build_plan_from_files(
                db, [row], str(root), str(out), ArchiveOptions()
            )
            pf = (
                await db.execute(select(PlanFile).where(PlanFile.plan_id == plan.id))
            ).scalar_one()

            def bad_copy(src, dst):
                with open(dst, "wb") as f:
                    f.write(b"truncated")

            monkeypatch.setattr(plan_executor.shutil, "copy2", bad_copy)

            media = (
                await db.execute(select(MediaFile).where(MediaFile.id == row.id))
            ).scalar_one()
            events = []
            async for event in run_plan(db, plan, [media], False, ""):
                events.append(event)
            assert events[-1]["errors"] == 1
            assert not (out / pf.target_rel_path).exists()
            await db.refresh(pf)
            assert pf.status == "failed"
            assert "校验失败" in (pf.error or "")
        finally:
            await db.close()
            await engine.dispose()

    asyncio.run(run())
