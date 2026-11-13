"""
归档操作接口（方案执行已统一到 /api/archive/plans/*）

GET  /api/archive/logs          - 获取本地归档操作记录
POST /api/archive/write-remarks - 为已归档文件写入备注
POST /api/archive/cleanup       - 删除原始文件（默认回收站，需二次确认）
"""
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.archive_plan import ArchivePlan, PlanFile
from app.models.file import MediaFile

try:
    from send2trash import send2trash as _recycle
except ImportError:  # pragma: no cover - requirements 已包含，防御性兜底
    _recycle = None

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================
# 请求/响应模型
# ============================================================

class CleanupRequest(BaseModel):
    source_folder: str = ""
    confirm: bool = False
    plan_id: int | None = None
    permanent: bool = False      # 默认进回收站；true 才永久删除


# ============================================================
# 数据库查询
# ============================================================

async def _load_db_files(db: AsyncSession, folder_path: str) -> list:
    """只匹配 folder_path 内部的文件，避免 C:/Photos 命中 C:/Photos2024。"""
    norm_folder = os.path.normpath(folder_path).rstrip("\\/")
    prefix = norm_folder + os.sep
    result = await db.execute(
        select(MediaFile)
        .where(MediaFile.original_path.like(f"{prefix}%"))
        .order_by(MediaFile.datetime_original)
    )
    return result.scalars().all()


@router.get("/archive/logs")
async def get_archive_logs(
    limit: int = Query(50, ge=1, le=200, description="最大返回条数"),
    db: AsyncSession = Depends(get_db),
):
    """获取本地归档操作记录（按时间倒序）"""
    from app.models.archive_log import ArchiveLog

    result = await db.execute(
        select(ArchiveLog)
        .order_by(ArchiveLog.created_at.desc())
        .limit(limit)
    )
    logs = result.scalars().all()

    return {
        "success": True,
        "data": {
            "logs": [
                {
                    "id": log.id,
                    "created_at": log.created_at,
                    "source_folder": log.source_folder,
                    "output_folder": log.output_folder,
                    "photo_count": log.photo_count,
                    "video_count": log.video_count,
                    "copied_count": log.copied_count,
                    "skipped_count": log.skipped_count,
                    "error_count": log.error_count,
                    "big_trips_count": log.big_trips_count,
                    "sub_trips_count": log.sub_trips_count,
                    "api_calls_used": log.api_calls_used,
                    "duration_sec": log.duration_sec,
                    "status": log.status,
                    "trip_log_generated": log.trip_log_generated,
                    "remarks_written": log.remarks_written,
                }
                for log in logs
            ],
            "total": len(logs),
        },
    }


# ============================================================
# 备注写入接口
# ============================================================

@router.post("/archive/write-remarks")
async def write_remarks(body: dict, db: AsyncSession = Depends(get_db)):
    """为已归档文件批量写入备注"""
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
                poi=f.poi or "",
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

def _delete_original_file(file: MediaFile, permanent: bool) -> str:
    """删除前的安全校验；返回状态字符串。"""
    if not file.current_path or file.current_path == file.original_path:
        return "skipped"
    if not os.path.exists(file.original_path):
        return "missing_source"
    if not os.path.exists(file.current_path):
        return "missing_target"
    try:
        if os.path.getsize(file.current_path) != os.path.getsize(file.original_path):
            return "size_mismatch"
    except OSError:
        return "stat_error"

    if permanent:
        os.remove(file.original_path)
    else:
        if _recycle is None:
            return "recycle_unavailable"
        _recycle(file.original_path)
    return "deleted"


@router.post("/archive/cleanup")
async def archive_cleanup(
    request: CleanupRequest,
    db: AsyncSession = Depends(get_db),
):
    """删除原始文件（需 confirm=True）。

    默认移入回收站；permanent=True 才永久删除。
    指定 plan_id 时只删除该方案中 status=copied 的源文件，并校验目标存在且 size 一致。
    """
    if not request.confirm:
        raise HTTPException(status_code=400, detail="请设置 confirm=true 确认删除操作")

    if request.plan_id is not None:
        plan = (
            await db.execute(select(ArchivePlan).where(ArchivePlan.id == request.plan_id))
        ).scalar_one_or_none()
        if not plan:
            raise HTTPException(status_code=404, detail=f"方案不存在: {request.plan_id}")
        if plan.status != "executed":
            raise HTTPException(status_code=400, detail="方案尚未执行，不能清理源文件")
        if request.source_folder and os.path.normpath(request.source_folder) != plan.source_folder:
            raise HTTPException(status_code=400, detail="source_folder 与方案不一致")
        db_files = (
            await db.execute(
                select(MediaFile)
                .join(PlanFile, PlanFile.media_file_id == MediaFile.id)
                .where(
                    PlanFile.plan_id == plan.id,
                    PlanFile.status == "copied",
                )
            )
        ).scalars().all()
    else:
        if not request.source_folder:
            raise HTTPException(status_code=400, detail="缺少 source_folder 或 plan_id")
        db_files = await _load_db_files(db, request.source_folder)

    deleted = errors = skipped = 0
    for f in db_files:
        try:
            status = _delete_original_file(f, request.permanent)
        except Exception as e:
            status = "error"
            logger.warning("删除原文件失败 %s: %s", f.original_path, e)

        if status == "deleted":
            deleted += 1
        elif status in ("skipped", "missing_source"):
            skipped += 1
        else:
            errors += 1
            logger.warning("跳过删除 %s: %s", f.original_path, status)

    return {
        "success": True,
        "deleted": deleted,
        "errors": errors,
        "skipped": skipped,
        "plan_id": request.plan_id,
        "mode": "permanent" if request.permanent else "recycle",
    }
