"""M3.2：清理原文件的安全校验"""
import asyncio
import os
import shutil

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.archive import CleanupRequest, archive_cleanup
from app.api.plans import ArchiveOptions
from app.api.plans import build_plan_from_files
from app.core.database import Base
from app.models import archive_log, archive_plan, file, trip, trip_record  # noqa: F401
from app.models.archive_plan import ArchivePlan, PlanFile
from app.models.file import MediaFile


async def make_db(tmp_path):
    db_path = (tmp_path / "cleanup.sqlite").as_posix()
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)()


async def make_ready_plan(db, tmp_path):
    root = tmp_path / "input"
    out = tmp_path / "out"
    root.mkdir()
    src = root / "IMG_0001.jpg"
    src.write_bytes(b"source-content")

    media = MediaFile(
        original_path=str(src),
        current_path=str(src),
        file_name=src.name,
        file_type="photo",
        datetime_original="2025-09-10T09:00:00",
        latitude=25.0,
        longitude=102.0,
        country="中国",
        province="",
        city="昆明",
        has_gps=True,
        needs_review=False,
        geocode_source="offline",
    )
    db.add(media)
    await db.commit()

    plan, _, _ = await build_plan_from_files(
        db, [media], str(root), str(out), ArchiveOptions()
    )
    pf = (
        await db.execute(select(PlanFile).where(PlanFile.plan_id == plan.id))
    ).scalar_one()
    target = out / pf.target_rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)
    media.current_path = str(target)
    pf.status = "copied"
    plan.status = "executed"
    await db.commit()
    return root, src, target, plan, media, pf


def test_cleanup_deletes_only_verified_plan_file(tmp_path):
    async def run():
        engine, db = await make_db(tmp_path)
        try:
            root, src, target, plan, media, pf = await make_ready_plan(db, tmp_path)

            # 另一个不在方案里的文件，不应被删除
            other_src = tmp_path / "other.jpg"
            other_src.write_bytes(b"other")
            other_target = tmp_path / "other_target.jpg"
            other_target.write_bytes(b"other")
            other = MediaFile(
                original_path=str(other_src),
                current_path=str(other_target),
                file_name="other.jpg",
                file_type="photo",
            )
            db.add(other)
            await db.commit()

            resp = await archive_cleanup(
                CleanupRequest(
                    source_folder=str(root),
                    confirm=True,
                    plan_id=plan.id,
                    permanent=True,
                ),
                db,
            )
            assert resp["success"] is True
            assert resp["deleted"] == 1
            assert not src.exists()
            assert target.exists()
            assert other_src.exists()
        finally:
            await db.close()
            await engine.dispose()

    asyncio.run(run())


def test_cleanup_refuses_size_mismatch(tmp_path):
    async def run():
        engine, db = await make_db(tmp_path)
        try:
            root, src, target, plan, media, pf = await make_ready_plan(db, tmp_path)
            target.write_bytes(b"different-length-content")

            resp = await archive_cleanup(
                CleanupRequest(
                    source_folder=str(root),
                    confirm=True,
                    plan_id=plan.id,
                    permanent=True,
                ),
                db,
            )
            assert resp["deleted"] == 0
            assert resp["errors"] == 1
            assert src.exists()
        finally:
            await db.close()
            await engine.dispose()

    asyncio.run(run())


def test_cleanup_refuses_missing_target(tmp_path):
    async def run():
        engine, db = await make_db(tmp_path)
        try:
            root, src, target, plan, media, pf = await make_ready_plan(db, tmp_path)
            target.unlink()

            resp = await archive_cleanup(
                CleanupRequest(
                    source_folder=str(root),
                    confirm=True,
                    plan_id=plan.id,
                    permanent=True,
                ),
                db,
            )
            assert resp["deleted"] == 0
            assert resp["errors"] == 1
            assert src.exists()
        finally:
            await db.close()
            await engine.dispose()

    asyncio.run(run())


def test_cleanup_defaults_to_recycle_bin(tmp_path, monkeypatch):
    async def run():
        engine, db = await make_db(tmp_path)
        try:
            root, src, target, plan, media, pf = await make_ready_plan(db, tmp_path)

            calls = []
            monkeypatch.setattr("app.api.archive._recycle", lambda p: calls.append(p) or os.remove(p))

            resp = await archive_cleanup(
                CleanupRequest(
                    source_folder=str(root),
                    confirm=True,
                    plan_id=plan.id,
                ),
                db,
            )
            assert resp["mode"] == "recycle"
            assert resp["deleted"] == 1
            assert calls == [str(src)]
            assert not src.exists()
        finally:
            await db.close()
            await engine.dispose()

    asyncio.run(run())
