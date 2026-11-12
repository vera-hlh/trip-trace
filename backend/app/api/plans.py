"""归档方案接口（M2）

- POST /api/archive/plans      生成方案（落库，不执行）
- GET  /api/archive/plans/{id} 读取方案树 + 文件明细

执行仍由 /api/archive/execute 负责；M2.4 会改为消费 plan_id。
"""
import json
import logging
import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
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
from app.services.plan_executor import load_plan_media, run_plan, source_snapshot

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================
# 请求模型
# ============================================================

class TripRename(BaseModel):
    trip_id: int
    display_name: str


class TripMerge(BaseModel):
    source_ids: list[int]
    target_id: int


class ContainerGroup(BaseModel):
    name: str
    sub_trip_ids: list[int]


class PlanPatchRequest(BaseModel):
    plan_version: int
    renames: list[TripRename] = []
    merges: list[TripMerge] = []
    containers: list[ContainerGroup] = []
    archive_mode: str | None = None


class PlanExecuteRequest(BaseModel):
    write_remarks: bool = False
    remark_template: str = "地点: {country}/{province}/{city}/{poi}"



# ============================================================
# 内部工具
# ============================================================

def _iso(value) -> str | None:
    return value.isoformat() if value else None


_ALLOWED_MODES = {"tree", "rebuild", "mixed"}


def _clean_name(value: str, field: str) -> str:
    """基础目录名校验；完整的 Windows 非法字符策略在 M3 统一处理。"""
    name = (value or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail=f"{field} 不能为空")
    if name in (".", "..") or any(ch in name for ch in '<>:"/\\|?*'):
        raise HTTPException(status_code=400, detail=f"{field} 含非法字符: {name}")
    if len(name) > 120:
        raise HTTPException(status_code=400, detail=f"{field} 过长（>120 字符）")
    return name


def _basename(path: str) -> str:
    """兼容 Windows/Unix 分隔符，从目标路径取文件名。"""
    return (path or "").replace("\\", "/").rstrip("/").split("/")[-1] or "file"


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


async def _plan_trip_map(db: AsyncSession, plan_id: int) -> dict[int, PlanTrip]:
    rows = (
        await db.execute(select(PlanTrip).where(PlanTrip.plan_id == plan_id))
    ).scalars().all()
    return {t.id: t for t in rows}


async def _recompute_plan_paths(db: AsyncSession, plan_id: int) -> None:
    """按当前树/容器重算所有 plan_files.target_rel_path。"""
    trips = await _plan_trip_map(db, plan_id)
    bigs = {t.id: t for t in trips.values() if t.kind == "big"}
    subs = {t.id: t for t in trips.values() if t.kind == "sub"}
    plan_files = (
        await db.execute(select(PlanFile).where(PlanFile.plan_id == plan_id))
    ).scalars().all()

    media_ids = [pf.media_file_id for pf in plan_files if pf.media_file_id]
    media_names: dict[int, str] = {}
    if media_ids:
        rows = (
            await db.execute(
                select(MediaFile.id, MediaFile.file_name)
                .where(MediaFile.id.in_(media_ids))
            )
        ).all()
        media_names = {row[0]: row[1] for row in rows}

    for pf in plan_files:
        sub = subs.get(pf.trip_id)
        if not sub or not sub.parent_id:
            continue
        big = bigs.get(sub.parent_id)
        if not big:
            continue
        file_name = media_names.get(pf.media_file_id) or _basename(pf.target_rel_path)
        parts = [big.folder_name]
        if sub.container_name:
            parts.append(sub.container_name)
        parts.extend([sub.folder_name, file_name])
        pf.target_rel_path = os.path.join(*parts)



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
        source_snapshot=source_snapshot(db_files),
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


@router.patch("/archive/plans/{plan_id}")
async def patch_plan(
    plan_id: int,
    body: PlanPatchRequest,
    db: AsyncSession = Depends(get_db),
):
    """编辑 draft 方案：重命名、合并、容器、归档模式。

    顺序：先 renames，再 merges，最后 containers / archive_mode。
    使用 plan_version 做乐观锁；冲突返回 409。
    """
    plan = (
        await db.execute(select(ArchivePlan).where(ArchivePlan.id == plan_id))
    ).scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail=f"方案不存在: {plan_id}")
    if plan.status != "draft":
        raise HTTPException(status_code=409, detail="只能编辑 draft 方案")
    if plan.plan_version != body.plan_version:
        raise HTTPException(
            status_code=409,
            detail=f"方案版本冲突：期望 {body.plan_version}，当前 {plan.plan_version}",
        )

    trips = await _plan_trip_map(db, plan_id)

    # 1. 重命名（同时改实际目录名，保证方案自包含）
    for item in body.renames:
        trip = trips.get(item.trip_id)
        if not trip:
            raise HTTPException(status_code=400, detail=f"行程不存在: {item.trip_id}")
        name = _clean_name(item.display_name, "display_name")
        trip.display_name = name
        trip.folder_name = name

    # 2. 合并
    for merge in body.merges:
        if not merge.source_ids:
            raise HTTPException(status_code=400, detail="source_ids 不能为空")
        if merge.target_id in merge.source_ids:
            raise HTTPException(status_code=400, detail="target_id 不能出现在 source_ids 中")
        target = trips.get(merge.target_id)
        if not target:
            raise HTTPException(status_code=400, detail=f"目标行程不存在: {merge.target_id}")

        for source_id in merge.source_ids:
            source = trips.get(source_id)
            if not source:
                raise HTTPException(status_code=400, detail=f"源行程不存在: {source_id}")
            if source.kind != target.kind:
                raise HTTPException(status_code=400, detail="只能合并同类型行程")
            if target.kind == "sub" and source.parent_id != target.parent_id:
                raise HTTPException(status_code=400, detail="子行程只能在同一大行程内合并")

            if target.kind == "big":
                # 大行程合并：把源大行程的子行程迁到目标大行程
                for t in trips.values():
                    if t.kind == "sub" and t.parent_id == source.id:
                        t.parent_id = target.id
                await db.flush()
            else:
                # 子行程合并：把源子行程的文件迁到目标子行程
                source_files = (
                    await db.execute(
                        select(PlanFile).where(
                            PlanFile.plan_id == plan_id,
                            PlanFile.trip_id == source.id,
                        )
                    )
                ).scalars().all()
                for pf in source_files:
                    pf.trip_id = target.id
                await db.flush()

            await db.delete(source)
            trips.pop(source_id, None)

    # 3. 容器分组（空 name 表示移出容器）
    assigned: set[int] = set()
    for group in body.containers:
        container_name = (
            _clean_name(group.name, "container_name") if group.name.strip() else None
        )
        for sub_id in group.sub_trip_ids:
            sub = trips.get(sub_id)
            if not sub or sub.kind != "sub":
                raise HTTPException(status_code=400, detail=f"子行程不存在: {sub_id}")
            if sub_id in assigned:
                raise HTTPException(status_code=400, detail=f"子行程重复分配: {sub_id}")
            assigned.add(sub_id)
            sub.container_name = container_name

    # 4. 归档模式（写入 options_json）
    if body.archive_mode is not None:
        if body.archive_mode not in _ALLOWED_MODES:
            raise HTTPException(status_code=400, detail=f"未知归档模式: {body.archive_mode}")
        try:
            options = json.loads(plan.options_json) if plan.options_json else {}
        except json.JSONDecodeError:
            options = {}
        options["archive_mode"] = body.archive_mode
        plan.options_json = json.dumps(options, ensure_ascii=False)

    await db.flush()
    await _recompute_plan_paths(db, plan_id)
    plan.plan_version += 1
    await db.commit()

    return {
        "success": True,
        "data": {
            "plan_id": plan.id,
            "plan_version": plan.plan_version,
            "status": plan.status,
        },
    }


@router.post("/archive/plans/{plan_id}/execute")
async def execute_plan(
    plan_id: int,
    body: PlanExecuteRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    """执行 draft 方案（SSE 进度）。

    - 只消费 plan 数据，不再重算切分；
    - 执行前校验 source_snapshot，源目录变化返回 409。
    """
    plan = (
        await db.execute(select(ArchivePlan).where(ArchivePlan.id == plan_id))
    ).scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail=f"方案不存在: {plan_id}")
    if plan.status != "draft":
        raise HTTPException(status_code=409, detail="只能执行 draft 方案")

    media = await load_plan_media(db, plan)
    if source_snapshot(media) != plan.source_snapshot:
        raise HTTPException(
            status_code=409,
            detail="源目录已变化，请重新生成方案后再执行",
        )

    request = body or PlanExecuteRequest()

    async def stream():
        try:
            async for event in run_plan(
                db,
                plan,
                media,
                request.write_remarks,
                request.remark_template,
            ):
                yield _sse(event)
        except Exception as exc:
            logger.error("执行方案失败: %s", exc, exc_info=True)
            yield _sse({"type": "fatal_error", "message": str(exc)})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
