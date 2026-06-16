"""
扫描文件夹接口

POST /api/scan
  - 递归扫描文件夹中的所有媒体文件
  - 提取每个文件的元数据（时间、GPS）
  - 存入 SQLite 数据库
  - 通过 SSE 流式推送进度

GET /api/scan/status
  - 获取当前数据库中已扫描的文件统计
"""
import asyncio
import json
import logging
import os
from datetime import datetime
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.file import MediaFile
from app.services.metadata_service import scan_folder, extract_metadata

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================
# 请求/响应模型
# ============================================================

class ScanRequest(BaseModel):
    folder_path: str
    options: dict = {}


class ScanStatusResponse(BaseModel):
    total_files: int
    with_gps: int
    without_gps: int
    needs_review: int
    videos: int
    photos: int


# ============================================================
# SSE 辅助函数
# ============================================================

def _sse_event(data: dict) -> str:
    """将字典序列化为 SSE 格式"""
    return f"data: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


# ============================================================
# 接口实现
# ============================================================

@router.post("/scan")
async def scan_folder_endpoint(
    request: ScanRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    扫描文件夹，提取所有媒体文件元数据（SSE 流式响应）

    SSE 事件类型：
      {"type": "start", "total": N}
      {"type": "progress", "current": N, "total": N, "file": "xxx.jpg",
       "has_gps": bool, "datetime": "2025-09-10T09:23:00"}
      {"type": "skip", "current": N, "total": N, "file": "xxx.jpg", "reason": "already_scanned"}
      {"type": "error", "file": "xxx.jpg", "message": "..."}
      {"type": "complete", "total_files": N, "with_gps": N, "without_gps": N, "errors": N}
    """
    folder_path = request.folder_path

    if not os.path.isdir(folder_path):
        raise HTTPException(status_code=400, detail=f"文件夹不存在: {folder_path}")

    async def generate() -> AsyncGenerator[str, None]:
        try:
            # 扫描文件列表
            yield _sse_event({"type": "scanning", "message": "正在枚举文件..."})
            await asyncio.sleep(0)  # 让出控制权，确保 SSE 先发出

            file_paths = scan_folder(folder_path)
            total = len(file_paths)

            if total == 0:
                yield _sse_event({"type": "complete", "total_files": 0,
                                  "with_gps": 0, "without_gps": 0, "errors": 0})
                return

            yield _sse_event({"type": "start", "total": total})

            # 统计
            with_gps = 0
            without_gps = 0
            errors = 0
            skipped = 0

            for idx, file_path in enumerate(file_paths, start=1):
                current = idx
                filename = os.path.basename(file_path)

                try:
                    # 检查是否已扫描（通过原始路径去重）
                    existing = await db.execute(
                        select(MediaFile).where(MediaFile.original_path == file_path)
                    )
                    if existing.scalar_one_or_none():
                        skipped += 1
                        yield _sse_event({
                            "type": "skip", "current": current, "total": total,
                            "file": filename, "reason": "already_scanned"
                        })
                        await asyncio.sleep(0)
                        continue

                    # 提取元数据
                    data = extract_metadata(file_path)
                    if data is None:
                        # 不支持的格式，跳过
                        yield _sse_event({
                            "type": "skip", "current": current, "total": total,
                            "file": filename, "reason": "unsupported_format"
                        })
                        await asyncio.sleep(0)
                        continue

                    # 存入数据库
                    media_file = MediaFile(
                        original_path=data.file_path,
                        current_path=data.file_path,
                        file_name=data.file_name,
                        file_type=data.file_type,
                        datetime_original=(
                            data.datetime_original.isoformat()
                            if data.datetime_original else None
                        ),
                        latitude=data.latitude,
                        longitude=data.longitude,
                        has_gps=data.has_gps,
                        needs_review=data.needs_review,
                    )
                    db.add(media_file)

                    # 每 50 个文件批量提交一次，减少 DB 开销
                    if idx % 50 == 0:
                        await db.flush()

                    if data.has_gps:
                        with_gps += 1
                    else:
                        without_gps += 1

                    if data.error:
                        errors += 1

                    yield _sse_event({
                        "type": "progress",
                        "current": current,
                        "total": total,
                        "file": filename,
                        "file_type": data.file_type,
                        "has_gps": data.has_gps,
                        "datetime": (
                            data.datetime_original.isoformat()
                            if data.datetime_original else None
                        ),
                        "error": data.error,
                    })

                except Exception as e:
                    errors += 1
                    logger.error(f"处理文件失败 {file_path}: {e}", exc_info=True)
                    yield _sse_event({
                        "type": "error",
                        "current": current,
                        "total": total,
                        "file": filename,
                        "message": str(e),
                    })

                await asyncio.sleep(0)  # 协作式多任务，保证 SSE 流畅推送

            # 最终提交所有未提交的记录
            await db.commit()

            yield _sse_event({
                "type": "complete",
                "total_files": total,
                "new_files": total - skipped,
                "skipped": skipped,
                "with_gps": with_gps,
                "without_gps": without_gps,
                "errors": errors,
            })

        except Exception as e:
            logger.error(f"扫描过程中发生未预期错误: {e}", exc_info=True)
            yield _sse_event({"type": "fatal_error", "message": str(e)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲，确保 SSE 实时推送
        },
    )


@router.get("/scan/status", response_model=ScanStatusResponse)
async def get_scan_status(db: AsyncSession = Depends(get_db)):
    """获取当前数据库中已扫描的文件统计"""
    try:
        total = (await db.execute(select(func.count(MediaFile.id)))).scalar() or 0
        with_gps = (
            await db.execute(
                select(func.count(MediaFile.id)).where(MediaFile.has_gps == True)  # noqa
            )
        ).scalar() or 0
        needs_review = (
            await db.execute(
                select(func.count(MediaFile.id)).where(MediaFile.needs_review == True)  # noqa
            )
        ).scalar() or 0
        videos = (
            await db.execute(
                select(func.count(MediaFile.id)).where(MediaFile.file_type == "video")
            )
        ).scalar() or 0

        return ScanStatusResponse(
            total_files=total,
            with_gps=with_gps,
            without_gps=total - with_gps,
            needs_review=needs_review,
            videos=videos,
            photos=total - videos,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/scan/clear")
async def clear_scan_data(db: AsyncSession = Depends(get_db)):
    """清空扫描数据（开发调试用）"""
    from sqlalchemy import delete
    await db.execute(delete(MediaFile))
    await db.commit()
    return {"success": True, "message": "扫描数据已清空"}


@router.post("/scan/geocode")
async def geocode_scanned_files(db: AsyncSession = Depends(get_db)):
    """
    对已扫描的有 GPS 但无城市信息的文件批量做逆地理编码
    返回更新数量统计
    """
    from app.services.geocode_service import reverse_geocode_offline

    # 查找有 GPS 但 city 为空的文件
    result = await db.execute(
        select(MediaFile).where(
            MediaFile.has_gps == True,
            MediaFile.city.is_(None)
        ).limit(500)  # 每次最多处理 500 个
    )
    files = result.scalars().all()

    if not files:
        return {"success": True, "updated": 0, "message": "无需要地理编码的文件"}

    from app.services.geocode_service import translate_cn_location

    updated = 0
    errors = 0
    for f in files:
        if not f.latitude or not f.longitude:
            continue
        try:
            loc = reverse_geocode_offline(f.latitude, f.longitude)
            if loc:
                # 对中国地名做中英文翻译
                if loc.country_code == "CN":
                    cn_city, cn_province = translate_cn_location(loc.city, loc.province)
                    # 格式：若有中文翻译则用"中文 (English)"，否则保留原英文
                    f.city = f"{cn_city} ({loc.city})" if cn_city != loc.city else loc.city
                    f.province = f"{cn_province} ({loc.province})" if cn_province != loc.province else loc.province
                else:
                    f.city = loc.city
                    f.province = loc.province
                f.country = loc.country
                f.district = loc.district
                updated += 1
        except Exception as e:
            errors += 1
            logger.warning(f"地理编码失败 {f.file_name}: {e}")

    await db.commit()

    return {
        "success": True,
        "updated": updated,
        "errors": errors,
        "total_processed": len(files),
        "message": f"已为 {updated} 个文件更新地理位置信息"
    }
