"""
归档操作接口

POST /api/archive/preview    - 预览归档方案（不执行文件操作）
POST /api/archive/execute    - 执行归档（复制模式，SSE 流式进度）
POST /api/archive/write-remarks - 为已归档文件写入备注
POST /api/archive/cleanup    - 删除原始文件（需用户二次确认）
"""
import asyncio
import json
import logging
import os
import shutil
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.file import MediaFile
from app.services.archive_service import (
    ArchiveConfig,
    MediaItem,
    segment_into_trips,
    generate_archive_preview,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================
# 请求/响应模型
# ============================================================

class ArchiveOptions(BaseModel):
    big_trip_threshold_days: int = 30
    small_trip_threshold_hours: float = 2.0
    granularity: str = "city"
    remark_template: str = "地点: {country}/{province}/{city}/{poi}"
    enable_gaode: bool = False
    gaode_api_key: str = ""


class ArchiveRequest(BaseModel):
    folder_path: str
    output_path: str
    options: ArchiveOptions = ArchiveOptions()


class SubTripOverride(BaseModel):
    """子行程重命名覆盖"""
    original_folder: str  # 算法生成的原始文件夹名
    display_name: str     # 用户修改后的文件夹名


class TripOverride(BaseModel):
    """大行程重命名覆盖（含子行程）"""
    original_folder: str
    display_name: str
    sub_overrides: list[SubTripOverride] = []


class ArchiveExecuteRequest(BaseModel):
    folder_path: str
    output_path: str
    options: ArchiveOptions = ArchiveOptions()
    write_remarks: bool = False
    remark_template: str = "地点: {country}/{province}/{city}"
    trip_overrides: list[TripOverride] = []


class CleanupRequest(BaseModel):
    source_folder: str
    confirm: bool = False


# ============================================================
# SSE 辅助函数
# ============================================================

def _sse_event(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


# ============================================================
# 从数据库查询文件（共用逻辑）
# ============================================================

async def _load_db_files(db: AsyncSession, folder_path: str) -> list:
    """从数据库加载指定文件夹的已扫描文件"""
    norm_folder = os.path.normpath(folder_path)

    from sqlalchemy import or_
    result = await db.execute(
        select(MediaFile).where(
            or_(
                MediaFile.original_path.like(f"{norm_folder}%"),
                MediaFile.original_path.like(f"{norm_folder.replace(chr(92), chr(92)*2)}%"),
                MediaFile.original_path.like(f"{norm_folder.replace(chr(92), '/')}%"),
            )
        ).order_by(MediaFile.datetime_original)
    )
    db_files = result.scalars().all()

    if not db_files:
        folder_name = os.path.basename(norm_folder)
        result2 = await db.execute(
            select(MediaFile).where(
                MediaFile.original_path.contains(folder_name)
            ).order_by(MediaFile.datetime_original)
        )
        db_files = result2.scalars().all()

    return db_files


def _build_media_items(db_files: list) -> list[MediaItem]:
    """将 DB 记录转为归档算法输入格式"""
    from datetime import datetime
    media_items = []
    for f in db_files:
        dt = None
        if f.datetime_original:
            try:
                dt = datetime.fromisoformat(f.datetime_original)
                if dt.tzinfo is not None:
                    dt = dt.replace(tzinfo=None)
            except (ValueError, AttributeError):
                pass

        location_key = ""
        if f.has_gps and f.city:
            location_key = f"{f.country or 'CN'}/{f.province or ''}/{f.city}"

        media_items.append(MediaItem(
            file_path=f.original_path,
            file_name=f.file_name,
            datetime_original=dt,
            location_key=location_key,
            city=f.city or "",
            country_code=f.country or "CN",
            has_gps=f.has_gps,
        ))
    return media_items


# ============================================================
# 归档预览接口
# ============================================================

@router.post("/archive/preview")
async def archive_preview(
    request: ArchiveRequest,
    db: AsyncSession = Depends(get_db),
):
    """预览归档方案（不执行任何文件操作）"""
    if not os.path.isdir(request.folder_path):
        raise HTTPException(status_code=400, detail=f"文件夹不存在: {request.folder_path}")

    try:
        db_files = await _load_db_files(db, request.folder_path)

        if not db_files:
            return {
                "success": True,
                "data": {
                    "preview": [],
                    "summary": {
                        "total_files": 0,
                        "trips_created": 0,
                        "files_without_gps": 0,
                        "files_needing_review": 0,
                        "message": "未找到已扫描的文件，请先执行扫描"
                    }
                }
            }

        opts = request.options
        config = ArchiveConfig(
            big_trip_threshold_days=opts.big_trip_threshold_days,
            small_trip_threshold_hours=opts.small_trip_threshold_hours,
        )

        media_items = _build_media_items(db_files)
        big_trips = segment_into_trips(media_items, config)
        preview_items = generate_archive_preview(big_trips, request.output_path)

        without_gps = sum(1 for f in db_files if not f.has_gps)
        needing_review = sum(1 for f in db_files if f.needs_review)
        total_sub_trips = sum(len(b.sub_trips) for b in big_trips)

        return {
            "success": True,
            "data": {
                "preview": [
                    {
                        "original_path": p.original_path,
                        "target_path": p.target_path,
                        "big_trip_folder": p.big_trip_folder,
                        "sub_trip_folder": p.sub_trip_folder,
                        "file_name": p.file_name,
                    }
                    for p in preview_items
                ],
                "trips_structure": [
                    {
                        "folder": b.folder_name,
                        "start_date": b.start_date.isoformat() if b.start_date else None,
                        "end_date": b.end_date.isoformat() if b.end_date else None,
                        "sub_trips": [
                            {
                                "folder": s.trip_name,
                                "location": s.location_label,
                                "start_date": s.start_date.isoformat() if s.start_date else None,
                                "end_date": s.end_date.isoformat() if s.end_date else None,
                                "file_count": s.file_count,
                            }
                            for s in b.sub_trips
                        ],
                        "total_files": b.total_files,
                    }
                    for b in big_trips
                ],
                "summary": {
                    "total_files": len(db_files),
                    "big_trips_created": len(big_trips),
                    "sub_trips_created": total_sub_trips,
                    "files_without_gps": without_gps,
                    "files_needing_review": needing_review,
                }
            }
        }

    except Exception as e:
        logger.error(f"生成归档预览失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 归档执行接口（复制模式，SSE 进度流）
# ============================================================

@router.post("/archive/execute")
async def archive_execute(
    request: ArchiveExecuteRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    执行归档（复制模式，不删除原文件）

    SSE 事件类型：
      {"type": "start",    "total": N, "output_path": "..."}
      {"type": "progress", "current": N, "total": N, "file": "...", "target_folder": "..."}
      {"type": "skip",     "current": N, "total": N, "file": "...", "reason": "already_exists"}
      {"type": "remark",   "current": N, "total": N, "file": "...", "success": bool}
      {"type": "error",    "current": N, "total": N, "file": "...", "message": "..."}
      {"type": "complete", "copied": N, "skipped": N, "errors": N, "output_path": "..."}
    """
    if not os.path.isdir(request.folder_path):
        raise HTTPException(status_code=400, detail=f"文件夹不存在: {request.folder_path}")

    async def generate() -> AsyncGenerator[str, None]:
        try:
            # 1. 从数据库获取文件
            yield _sse_event({"type": "preparing", "message": "正在准备归档方案..."})
            await asyncio.sleep(0)

            db_files = await _load_db_files(db, request.folder_path)
            if not db_files:
                yield _sse_event({"type": "fatal_error", "message": "未找到已扫描的文件，请先扫描"})
                return

            # 2. 运行归档算法
            opts = request.options
            config = ArchiveConfig(
                big_trip_threshold_days=opts.big_trip_threshold_days,
                small_trip_threshold_hours=opts.small_trip_threshold_hours,
            )
            media_items = _build_media_items(db_files)
            big_trips = segment_into_trips(media_items, config)
            preview_items = generate_archive_preview(big_trips, request.output_path)

            # 3. 构建重命名覆盖映射
            # big_override:  { 原始大行程文件夹名 → 用户文件夹名 }
            # sub_override:  { (原始大行程名, 原始子行程名) → 用户子行程名 }
            big_override: dict[str, str] = {}
            sub_override: dict[tuple[str, str], str] = {}

            for o in request.trip_overrides:
                if o.display_name and o.display_name != o.original_folder:
                    big_override[o.original_folder] = o.display_name
                for s in o.sub_overrides:
                    if s.display_name and s.display_name != s.original_folder:
                        sub_override[(o.original_folder, s.original_folder)] = s.display_name

            # 4. 应用覆盖，更新目标路径
            for item in preview_items:
                real_big = big_override.get(item.big_trip_folder, item.big_trip_folder)
                real_sub = sub_override.get(
                    (item.big_trip_folder, item.sub_trip_folder),
                    item.sub_trip_folder
                )
                item.big_trip_folder = real_big
                item.sub_trip_folder = real_sub
                item.target_path = os.path.join(
                    request.output_path, real_big, real_sub, item.file_name
                )

            total = len(preview_items)
            yield _sse_event({
                "type": "start",
                "total": total,
                "output_path": request.output_path
            })

            # 5. 执行文件复制
            copied = 0
            skipped = 0
            errors = 0
            remark_ok = 0

            for idx, item in enumerate(preview_items, 1):
                await asyncio.sleep(0)

                try:
                    # 创建目标目录
                    target_dir = os.path.dirname(item.target_path)
                    os.makedirs(target_dir, exist_ok=True)

                    # 跳过已存在的文件
                    if os.path.exists(item.target_path):
                        skipped += 1
                        yield _sse_event({
                            "type": "skip",
                            "current": idx, "total": total,
                            "file": item.file_name,
                            "reason": "already_exists"
                        })
                        continue

                    # 复制文件（保留元数据）
                    shutil.copy2(item.original_path, item.target_path)
                    copied += 1

                    # 可选：写入备注到已复制的文件
                    if request.write_remarks and request.remark_template:
                        try:
                            from app.services.remark_service import write_remark, format_remark
                            # 查询该文件的地理信息
                            db_result = await db.execute(
                                select(MediaFile).where(
                                    MediaFile.original_path == item.original_path
                                )
                            )
                            media_file = db_result.scalar_one_or_none()
                            if media_file:
                                remark_text = format_remark(
                                    request.remark_template,
                                    country=media_file.country or "",
                                    province=media_file.province or "",
                                    city=media_file.city or "",
                                    district=getattr(media_file, "district", "") or "",
                                    poi="",
                                    trip_name=item.big_trip_folder,
                                    sub_trip_name=item.sub_trip_folder,
                                )
                                if remark_text:
                                    result = write_remark(item.target_path, remark_text)
                                    if result.success:
                                        remark_ok += 1
                            yield _sse_event({
                                "type": "remark",
                                "current": idx, "total": total,
                                "file": item.file_name,
                                "success": True
                            })
                        except Exception as re:
                            logger.warning(f"写入备注失败 {item.file_name}: {re}")
                            yield _sse_event({
                                "type": "remark",
                                "current": idx, "total": total,
                                "file": item.file_name,
                                "success": False
                            })

                    # 更新数据库 current_path
                    db_result = await db.execute(
                        select(MediaFile).where(
                            MediaFile.original_path == item.original_path
                        )
                    )
                    media_file = db_result.scalar_one_or_none()
                    if media_file:
                        media_file.current_path = item.target_path

                    yield _sse_event({
                        "type": "progress",
                        "current": idx, "total": total,
                        "file": item.file_name,
                        "target_folder": f"{item.big_trip_folder}/{item.sub_trip_folder}"
                    })

                except Exception as e:
                    errors += 1
                    logger.error(f"复制失败 {item.original_path}: {e}")
                    yield _sse_event({
                        "type": "error",
                        "current": idx, "total": total,
                        "file": item.file_name,
                        "message": str(e)
                    })

                # 每 50 个文件批量提交
                if idx % 50 == 0:
                    await db.flush()

            # 最终提交
            await db.commit()

            yield _sse_event({
                "type": "complete",
                "total_files": total,
                "copied": copied,
                "skipped": skipped,
                "errors": errors,
                "remarks_written": remark_ok,
                "output_path": request.output_path,
            })

        except Exception as e:
            logger.error(f"执行归档时发生错误: {e}", exc_info=True)
            yield _sse_event({"type": "fatal_error", "message": str(e)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ============================================================
# 备注写入接口
# ============================================================

@router.post("/archive/write-remarks")
async def write_remarks(body: dict, db: AsyncSession = Depends(get_db)):
    """为已归档文件批量写入备注（可独立调用）"""
    folder_path = body.get("folder_path", "")
    template = body.get("template", "地点: {country}/{province}/{city}")

    if not folder_path or not os.path.isdir(folder_path):
        raise HTTPException(status_code=400, detail="folder_path 无效")

    from app.services.remark_service import write_remark, format_remark

    db_files = await _load_db_files(db, folder_path)
    ok = 0
    fail = 0

    for f in db_files:
        target = f.current_path or f.original_path
        if not os.path.exists(target):
            continue
        try:
            remark_text = format_remark(
                template,
                country=f.country or "",
                province=f.province or "",
                city=f.city or "",
                district=getattr(f, "district", "") or "",
            )
            if remark_text:
                result = write_remark(target, remark_text)
                if result.success:
                    ok += 1
                else:
                    fail += 1
        except Exception as e:
            fail += 1
            logger.warning(f"备注写入失败 {target}: {e}")

    return {"success": True, "ok": ok, "fail": fail}


# ============================================================
# 清理原文件接口
# ============================================================

@router.post("/archive/cleanup")
async def archive_cleanup(
    request: CleanupRequest,
    db: AsyncSession = Depends(get_db),
):
    """删除原始文件（需用户显式确认 confirm=True）"""
    if not request.confirm:
        raise HTTPException(status_code=400, detail="请设置 confirm=true 确认删除操作")

    db_files = await _load_db_files(db, request.source_folder)
    deleted = 0
    errors = 0

    for f in db_files:
        if f.current_path and f.current_path != f.original_path:
            # 已归档到新路径，可以删除原文件
            try:
                if os.path.exists(f.original_path):
                    os.remove(f.original_path)
                    deleted += 1
            except Exception as e:
                errors += 1
                logger.warning(f"删除原文件失败 {f.original_path}: {e}")

    return {"success": True, "deleted": deleted, "errors": errors}
