"""M3.2b：目录名净化与路径前缀匹配"""
import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.archive import _load_db_files
from app.api.plans import ArchiveOptions
from app.api.plans import PlanPatchRequest, TripRename, build_plan_from_files, patch_plan
from app.core.database import Base
from app.models import archive_log, archive_plan, file, trip, trip_record  # noqa: F401
from app.models.archive_plan import PlanTrip
from app.models.file import MediaFile
from app.utils.path_utils import sanitize_folder_name, validate_folder_name


def test_folder_name_sanitize_and_validate():
    assert sanitize_folder_name("A/B:C*?") == "A_B_C__"
    assert sanitize_folder_name("CON") == "_CON"
    assert sanitize_folder_name("  name.  ") == "name"
    assert sanitize_folder_name("", "fallback") == "fallback"

    assert validate_folder_name("  ok  ") == "ok"
    assert validate_folder_name("name.") == "name"
    with pytest.raises(ValueError):
        validate_folder_name("CON")
    with pytest.raises(ValueError):
        validate_folder_name("a/b")


def test_prefix_match_does_not_leak_sibling_folder(tmp_path):
    async def run():
        db_path = (tmp_path / "prefix.sqlite").as_posix()
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        photos = tmp_path / "photos"
        photos2 = tmp_path / "photos2"
        photos.mkdir()
        photos2.mkdir()

        async with session_factory() as db:
            db.add(MediaFile(
                original_path=str(photos / "a.jpg"),
                current_path=str(photos / "a.jpg"),
                file_name="a.jpg",
                file_type="photo",
            ))
            db.add(MediaFile(
                original_path=str(photos2 / "b.jpg"),
                current_path=str(photos2 / "b.jpg"),
                file_name="b.jpg",
                file_type="photo",
            ))
            await db.commit()

            files = await _load_db_files(db, str(photos))
            assert [f.file_name for f in files] == ["a.jpg"]

        await engine.dispose()

    asyncio.run(run())


def test_plan_sanitizes_generated_names_and_rejects_reserved(tmp_path):
    async def run():
        db_path = (tmp_path / "sanitize.sqlite").as_posix()
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        root = tmp_path / "input"
        root.mkdir()
        src = root / "IMG_0001.jpg"
        src.write_bytes(b"x")

        async with session_factory() as db:
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
                poi="A/B",
                has_gps=True,
                needs_review=False,
                geocode_source="offline",
            )
            db.add(media)
            await db.commit()

            plan, _, _ = await build_plan_from_files(
                db, [media], str(root), str(tmp_path / "out"), ArchiveOptions()
            )
            sub = (
                await db.execute(select(PlanTrip).where(PlanTrip.plan_id == plan.id, PlanTrip.kind == "sub"))
            ).scalar_one()
            assert "/" not in sub.folder_name
            assert "A_B" in sub.folder_name

            with pytest.raises(HTTPException) as exc:
                await patch_plan(
                    plan.id,
                    PlanPatchRequest(
                        plan_version=1,
                        renames=[TripRename(trip_id=sub.id, display_name="CON")],
                    ),
                    db,
                )
            assert exc.value.status_code == 400

        await engine.dispose()

    asyncio.run(run())
