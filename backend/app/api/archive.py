"""
归档操作接口

POST /api/archive/preview    - 预览归档方案（不执行文件操作）
POST /api/archive/execute    - 执行归档（复制模式，保留原文件）
POST /api/archive/write-remarks - 为已归档文件写入备注
POST /api/archive/cleanup    - 删除原始文件（需用户二次确认）
"""
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.file import MediaFile
from app.models.trip import Trip
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
    granularity: str = "city"       # "city" | "poi"
    remark_template: str = "地点: {country}/{province}/{city}/{poi}"
    enable_gaode: bool = False
    gaode_api_key: str = ""


class ArchiveRequest(BaseModel):
    folder_path: str
    output_path: str
    options: ArchiveOptions = ArchiveOptions()


class CleanupRequest(BaseModel):
    source_folder: str
    confirm: bool = False


# ============================================================
# 归档预览接口
# ============================================================

@router.post("/archive/preview")
async def archive_preview(
    request: ArchiveRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    预览归档方案

    基于已扫描到数据库的文件元数据，生成归档方案（不执行任何文件操作）。
    用户可审查预览结果后再决定是否执行。

    Returns:
        归档预览列表 + 摘要统计
    """
    if not os.path.isdir(request.folder_path):
        raise HTTPException(status_code=400, detail=f"文件夹不存在: {request.folder_path}")

    try:
        # 路径规范化（处理双反斜杠、正斜杠等混用问题）
        import os
        norm_folder = os.path.normpath(request.folder_path)

        # 从数据库获取已扫描的文件
        # 使用多种路径格式匹配（兼容 Windows 反斜杠存储差异）
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

        # 如果还是没有结果，做宽松匹配（取路径最后部分）
        if not db_files:
            folder_name = os.path.basename(norm_folder)
            result2 = await db.execute(
                select(MediaFile).where(
                    MediaFile.original_path.contains(folder_name)
                ).order_by(MediaFile.datetime_original)
            )
            db_files = result2.scalars().all()

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

        # 转换为归档算法的输入格式
        opts = request.options
        config = ArchiveConfig(
            big_trip_threshold_days=opts.big_trip_threshold_days,
            small_trip_threshold_hours=opts.small_trip_threshold_hours,
        )

        media_items = []
        for f in db_files:
            from datetime import datetime
            dt = None
            if f.datetime_original:
                try:
                    dt = datetime.fromisoformat(f.datetime_original)
                except ValueError:
                    pass

            # 构建地点键（用于行程切分）
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

        # 运行归档算法
        big_trips = segment_into_trips(media_items, config)

        # 生成预览
        preview_items = generate_archive_preview(big_trips, request.output_path)

        # 统计
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
# 归档执行接口（复制模式）
# ============================================================

@router.post("/archive/execute")
async def archive_execute(
    request: ArchiveRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    执行归档（复制模式，不删除原文件）

    TODO: Phase 2 Week 5 实现
    """
    return {"success": False, "error": "TODO: 待 Week 5 实现文件复制操作"}


# ============================================================
# 备注写入接口
# ============================================================

@router.post("/archive/write-remarks")
async def write_remarks(body: dict, db: AsyncSession = Depends(get_db)):
    """
    为已归档文件写入备注字段

    TODO: Phase 2 Week 5 实现
    """
    return {"success": False, "error": "TODO: 待 Week 5 实现备注写入"}


# ============================================================
# 清理原文件接口
# ============================================================

@router.post("/archive/cleanup")
async def archive_cleanup(
    request: CleanupRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    删除原始文件（需用户显式确认 confirm=True）

    TODO: Phase 2 Week 5 实现
    """
    if not request.confirm:
        raise HTTPException(status_code=400, detail="请设置 confirm=true 确认删除操作")
    return {"success": False, "error": "TODO: 待 Week 5 实现文件删除操作"}
