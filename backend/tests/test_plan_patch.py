"""归档方案编辑测试（M2.3）：重命名、合并、容器、版本冲突"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.plans import ArchiveOptions
from app.api.plans import (
    ContainerGroup,
    PlanPatchRequest,
    TripMerge,
    TripRename,
    build_plan_from_files,
    get_plan,
    patch_plan,
)
from app.core.database import Base
from app.models import archive_plan, file, trip  # noqa: F401  注册表
from app.models.archive_plan import ArchivePlan, PlanFile, PlanTrip


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


async def make_context(tmp_path):
    db_path = (tmp_path / "patch.sqlite").as_posix()
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, session_factory()


def test_patch_rename_merge_container(tmp_path):
    async def run():
        engine, db = await make_context(tmp_path)
        try:
            db_files = [
                make_file(1, "k1.jpg", "2025-09-10T09:00:00", "昆明"),
                make_file(2, "k2.jpg", "2025-09-10T11:00:00", "昆明"),
                make_file(3, "d1.jpg", "2025-10-25T09:00:00", "大理"),
            ]
            plan, big_count, sub_count = await build_plan_from_files(
                db, db_files, "C:/in", "C:/out", ArchiveOptions()
            )
            assert (big_count, sub_count) == (2, 2)

            data = (await get_plan(plan.id, db))["data"]
            big1, big2 = data["trips_structure"]
            sub1, sub2 = big1["sub_trips"][0], big2["sub_trips"][0]

            # 1) 大行程合并：big2 → big1
            resp = await patch_plan(
                plan.id,
                PlanPatchRequest(
                    plan_version=1,
                    merges=[TripMerge(source_ids=[big2["id"]], target_id=big1["id"])],
                ),
                db,
            )
            assert resp["data"]["plan_version"] == 2

            data = (await get_plan(plan.id, db))["data"]
            assert len(data["trips_structure"]) == 1
            big1 = data["trips_structure"][0]
            assert big1["total_files"] == 3
            assert len(big1["sub_trips"]) == 2
            assert all(f["target_rel_path"].startswith(big1["folder"]) for f in data["files"])

            # 2) 子行程合并：sub2 → sub1
            sub1, sub2 = big1["sub_trips"]
            resp = await patch_plan(
                plan.id,
                PlanPatchRequest(
                    plan_version=2,
                    merges=[TripMerge(source_ids=[sub2["id"]], target_id=sub1["id"])],
                ),
                db,
            )
            assert resp["data"]["plan_version"] == 3

            data = (await get_plan(plan.id, db))["data"]
            big1 = data["trips_structure"][0]
            assert len(big1["sub_trips"]) == 1
            assert len(data["files"]) == 3
            assert all(f["trip_id"] == big1["sub_trips"][0]["id"] for f in data["files"])

            # 3) 容器
            sub_id = big1["sub_trips"][0]["id"]
            resp = await patch_plan(
                plan.id,
                PlanPatchRequest(
                    plan_version=3,
                    containers=[ContainerGroup(name="漠河之行", sub_trip_ids=[sub_id])],
                ),
                db,
            )
            assert resp["data"]["plan_version"] == 4
            data = (await get_plan(plan.id, db))["data"]
            assert all("漠河之行" in f["target_rel_path"] for f in data["files"])

            # 4) 重命名大行程
            resp = await patch_plan(
                plan.id,
                PlanPatchRequest(
                    plan_version=4,
                    renames=[TripRename(trip_id=big1["id"], display_name="东北之行")],
                ),
                db,
            )
            assert resp["data"]["plan_version"] == 5
            data = (await get_plan(plan.id, db))["data"]
            assert data["trips_structure"][0]["folder"] == "东北之行"
            assert all(f["target_rel_path"].startswith("东北之行") for f in data["files"])

            # 5) 非法目录名：draft 状态下应在修改前拒绝
            with pytest.raises(HTTPException) as exc:
                await patch_plan(
                    plan.id,
                    PlanPatchRequest(
                        plan_version=5,
                        renames=[TripRename(trip_id=big1["id"], display_name="..")],
                    ),
                    db,
                )
            assert exc.value.status_code == 400

            # 6) 版本冲突
            with pytest.raises(HTTPException) as exc:
                await patch_plan(
                    plan.id,
                    PlanPatchRequest(plan_version=1, archive_mode="tree"),
                    db,
                )
            assert exc.value.status_code == 409

            # 7) 归档模式写入 options
            resp = await patch_plan(
                plan.id,
                PlanPatchRequest(plan_version=5, archive_mode="mixed"),
                db,
            )
            assert resp["data"]["plan_version"] == 6
            data = (await get_plan(plan.id, db))["data"]
            assert data["plan"]["options"]["archive_mode"] == "mixed"

            # 8) 已执行方案不可编辑
            plan_row = (
                await db.execute(select(ArchivePlan).where(ArchivePlan.id == plan.id))
            ).scalar_one()
            plan_row.status = "executed"
            await db.commit()
            with pytest.raises(HTTPException) as exc:
                await patch_plan(
                    plan.id,
                    PlanPatchRequest(plan_version=6, archive_mode="tree"),
                    db,
                )
            assert exc.value.status_code == 409
        finally:
            await db.close()
            await engine.dispose()

    asyncio.run(run())
