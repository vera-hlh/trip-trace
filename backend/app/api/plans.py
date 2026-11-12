"""归档方案接口（M2）

- POST /api/archive/plans      生成方案（落库，不执行）
- GET  /api/archive/plans/{id} 读取方案树 + 文件明细

执行仍由 /api/archive/execute 负责；M2.4 会改为消费 plan_id。
"""
import hashlib
import json
import logging
import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.archive import (
    ArchiveOptions,
    ArchiveRequest,
    _build_media_items,
    _load_db_files,
)
from app.core.database import get_db
from app.models.archive_plan import ArchivePlan, PlanFile, PlanTrip
from app.models.file import MediaFile
from app.services.archive_service import (
    ArchiveConfig,
    infer_location_for_gps_less,
    segment_into_trips,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================
# 内部工具
# ============================================================

def _source_snapshot(db_files: list) -> str:
    """文件集合指纹：路径 + size + mtime_ns，用于检测预览后源目录变化。"""
    digest = hashlib.sha256()
    for f in sorted(db_files, key=lambda x: x.original_path):
        try:
            stat = os.stat(f.original_path)
            signature = f"{f.original_path}|{stat.st_size}|{stat.st_mtime_ns}"
        except OSError:
            signature = f"{f.original_path}|missing"
        digest.update(signature.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _iso(value) -> str | None:
    return value.isoformat() if value else None


async def build_plan_from_files(
    db: AsyncSession,
    db_files: list,
    source_folder: str,
    output_folder: str,
    options: ArchiveOptions,
) -> tuple[ArchivePlan, int, int]:
    """把当前扫描结果生成一个 draft 方案并落库。

    Returns:
        (plan, big_trips_count, sub_trips_count)
    """
    config = ArchiveConfig(
        big_trip_threshold_days=options.big_trip_threshold_days,
        small_trip_threshold_hours=options.small_trip_threshold_hours,
    )

    media_items = _build_media_items(db_files)
    media_items = infer_location_for_gps_less(
        media_items, options.small_trip_threshold_hours
    )
    big_trips = segment_into_trips(media_items, config)

    # 不把 API Key 写进方案
    option_payload = options.model_dump()
    option_payload.pop("gaode_api_key", None)

    plan = ArchivePlan(
        source_folder=os.path.normpath(source_folder),
        output_folder=os.path.normpath(output_folder),
        options_json=json.dumps(option_payload, ensure_ascii=False),
        status="draft",
        plan_version=1,
        source_snapshot=_source_snapshot(db_files),
        created_at=datetime.now().isoformat(timespec="seconds"),
    )
    db.add(plan)
    await db.flush()

    path_to_media_id = {f.original_path: f.id for f in db_files}
    sub_count = 0

    for big_index, big in enumerate(big_trips):
        big_row = PlanTrip(
            plan_id=plan.id,
            kind="big",
            folder_name=big.folder_name,
            display_name=big.display_name or big.folder_name,
            start_date=_iso(big.start_date),
            end_date=_iso(big.end_date),
            sort_order=big_index,
        )
        db.add(big_row)
        await db.flush()

        for sub_index, sub in enumerate(big.sub_trips):
            sub_row = PlanTrip(
                plan_id=plan.id,
                parent_id=big_row.id,
                kind="sub",
                folder_name=sub.trip_name,
                display_name=sub.trip_name,
                start_date=_iso(sub.start_date),
                end_date=_iso(sub.end_date),
                sequence_num=sub.sequence_num,
                location_label=sub.location_label,
                sort_order=sub_index,
            )
            db.add(sub_row)
            await db.flush()
            sub_count += 1

            for item in sub.items:
                db.add(PlanFile(
                    plan_id=plan.id,
                    trip_id=sub_row.id,
                    media_file_id=path_to_media_id.get(item.file_path),
                    target_rel_path=os.path.join(
                        big.folder_name, sub.trip_name, item.file_name
                    ),
                    status="pending",
                ))

    await db.commit()
    await db.refresh(plan)
    return plan, len(big_trips), sub_count


# ============================================================
# 接口
# ============================================================

@router.post("/archive/plans")
async def create_plan(
    request: ArchiveRequest,
    db: AsyncSession = Depends(get_db),
):
    """根据已扫描文件生成归档方案（draft），不复制任何文件。"""
    if not os.path.isdir(request.folder_path):
        raise HTTPException(status_code=400, detail=f"文件夹不存在: {request.folder_path}")

    db_files = await _load_db_files(db, request.folder_path)
    if not db_files:
        raise HTTPException(status_code=400, detail="未找到已扫描的文件，请先执行扫描")

    try:
        plan, big_count, sub_count = await build_plan_from_files(
            db,
            db_files,
            request.folder_path,
            request.output_path,
            request.options,
        )
    except Exception as exc:
        logger.error("生成归档方案失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"生成方案失败: {exc}")

    return {
        "success": True,
        "data": {
            "plan_id": plan.id,
            "status": plan.status,
            "plan_version": plan.plan_version,
            "source_snapshot": plan.source_snapshot,
            "big_trips": big_count,
            "sub_trips": sub_count,
            "files": len(db_files),
        },
    }


@router.get("/archive/plans/{plan_id}")
async def get_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
):
    """读取方案：行程树 + 文件明细。"""
    plan = (
        await db.execute(select(ArchivePlan).where(ArchivePlan.id == plan_id))
    ).scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail=f"方案不存在: {plan_id}")

    trips = (
        await db.execute(
            select(PlanTrip)
            .where(PlanTrip.plan_id == plan_id)
            .order_by(PlanTrip.sort_order, PlanTrip.sequence_num, PlanTrip.id)
        )
    ).scalars().all()

    file_rows = (
        await db.execute(
            select(
                PlanFile,
                MediaFile.file_name,
                MediaFile.original_path,
            )
            .outerjoin(MediaFile, PlanFile.media_file_id == MediaFile.id)
            .where(PlanFile.plan_id == plan_id)
            .order_by(PlanFile.id)
        )
    ).all()

    counts: dict[int, int] = {}
    files = []
    for plan_file, file_name, original_path in file_rows:
        counts[plan_file.trip_id] = counts.get(plan_file.trip_id, 0) + 1
        files.append({
            "id": plan_file.id,
            "trip_id": plan_file.trip_id,
            "media_file_id": plan_file.media_file_id,
            "target_rel_path": plan_file.target_rel_path,
            "status": plan_file.status,
            "error": plan_file.error,
            "file_name": file_name,
            "original_path": original_path,
        })

    big_rows = [t for t in trips if t.kind == "big"]
    sub_by_parent: dict[int, list] = {}
    for t in trips:
        if t.kind == "sub" and t.parent_id is not None:
            sub_by_parent.setdefault(t.parent_id, []).append(t)

    trips_structure = []
    for big in big_rows:
        subs = []
        for sub in sub_by_parent.get(big.id, []):
            subs.append({
                "id": sub.id,
                "folder": sub.folder_name,
                "display_name": sub.display_name or sub.folder_name,
                "location": sub.location_label or "",
                "start_date": sub.start_date,
                "end_date": sub.end_date,
                "sequence_num": sub.sequence_num,
                "file_count": counts.get(sub.id, 0),
            })
        trips_structure.append({
            "id": big.id,
            "folder": big.folder_name,
            "display_name": big.display_name or big.folder_name,
            "start_date": big.start_date,
            "end_date": big.end_date,
            "total_files": sum(s["file_count"] for s in subs),
            "sub_trips": subs,
        })

    try:
        options = json.loads(plan.options_json) if plan.options_json else {}
    except json.JSONDecodeError:
        options = {}

    return {
        "success": True,
        "data": {
            "plan": {
                "id": plan.id,
                "source_folder": plan.source_folder,
                "output_folder": plan.output_folder,
                "status": plan.status,
                "plan_version": plan.plan_version,
                "source_snapshot": plan.source_snapshot,
                "created_at": plan.created_at,
                "executed_at": plan.executed_at,
                "options": options,
            },
            "trips_structure": trips_structure,
            "files": files,
        },
    }
