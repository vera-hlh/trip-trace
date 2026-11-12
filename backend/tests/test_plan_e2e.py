"""M2 端到端验证：生成方案 → 重命名/容器/大行程合并 → 执行 → 检查磁盘"""
import asyncio
import os

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.main import app
from app.models import archive_log, archive_plan, file, trip, trip_record  # noqa: F401
from app.models.archive_log import ArchiveLog
from app.models.file import MediaFile
from app.models.trip_record import TripRecord


async def make_db(tmp_path):
    db_path = (tmp_path / "e2e.sqlite").as_posix()
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)()


async def add_media(db, folder, name, dt, city):
    path = folder / name
    path.write_bytes(b"fake-" + name.encode())
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


def test_full_plan_flow(tmp_path):
    async def run():
        engine, db = await make_db(tmp_path)
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()

        try:
            rows = [
                await add_media(db, input_dir, "k1.jpg", "2025-09-10T09:00:00", "昆明"),
                await add_media(db, input_dir, "k2.jpg", "2025-09-10T11:00:00", "昆明"),
                await add_media(db, input_dir, "d1.jpg", "2025-11-01T09:00:00", "大理"),
            ]
            await db.commit()

            async def override_get_db():
                yield db

            app.dependency_overrides[get_db] = override_get_db
            try:
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    created = await client.post(
                        "/api/archive/plans",
                        json={
                            "folder_path": str(input_dir),
                            "output_path": str(output_dir),
                            "options": {
                                "big_trip_threshold_days": 30,
                                "small_trip_threshold_hours": 2.0,
                            },
                        },
                    )
                    assert created.status_code == 200, created.text
                    plan_id = created.json()["data"]["plan_id"]

                    detail = await client.get(f"/api/archive/plans/{plan_id}")
                    assert detail.status_code == 200
                    data = detail.json()["data"]
                    assert len(data["trips_structure"]) == 2

                    big1, big2 = data["trips_structure"]
                    sub1 = big1["sub_trips"][0]

                    patch = await client.patch(
                        f"/api/archive/plans/{plan_id}",
                        json={
                            "plan_version": 1,
                            "renames": [
                                {"trip_id": sub1["id"], "display_name": "昆明改"}
                            ],
                            "merges": [
                                {
                                    "source_ids": [big2["id"]],
                                    "target_id": big1["id"],
                                }
                            ],
                            "containers": [
                                {
                                    "name": "漠河之行",
                                    "sub_trip_ids": [sub1["id"]],
                                }
                            ],
                        },
                    )
                    assert patch.status_code == 200, patch.text
                    assert patch.json()["data"]["plan_version"] == 2

                    executed = await client.post(
                        f"/api/archive/plans/{plan_id}/execute", json={}
                    )
                    assert executed.status_code == 200, executed.text
                    assert '"type": "complete"' in executed.text
                    assert '"errors": 0' in executed.text

                    after = await client.get(f"/api/archive/plans/{plan_id}")
                    assert after.status_code == 200
                    after_data = after.json()["data"]
                    assert after_data["plan"]["status"] == "executed"
                    assert len(after_data["trips_structure"]) == 1
            finally:
                app.dependency_overrides.clear()

            # 磁盘结构：只剩合并后的大行程；容器/重命名生效
            big_dirs = [p for p in output_dir.iterdir() if p.is_dir()]
            assert len(big_dirs) == 1
            big_dir = big_dirs[0]
            assert (big_dir / "trip_log.md").exists()

            sub1_dir = big_dir / "漠河之行" / "昆明改"
            assert (sub1_dir / "k1.jpg").exists()
            assert (sub1_dir / "k2.jpg").exists()

            # 被合并进来的大理子行程仍在，且其文件已落到目标大行程下
            dali_files = list(big_dir.rglob("d1.jpg"))
            assert len(dali_files) == 1
            assert dali_files[0].parent.parent == big_dir

            logs = (await db.execute(select(ArchiveLog))).scalars().all()
            assert len(logs) == 1
            assert logs[0].copied_count == 3

            records = (await db.execute(select(TripRecord))).scalars().all()
            assert len(records) == 1
            assert records[0].sub_trip_count == 2
            assert records[0].total_files == 3
        finally:
            await db.close()
            await engine.dispose()

    asyncio.run(run())
