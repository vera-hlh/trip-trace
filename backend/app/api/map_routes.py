"""
地图生成接口

GET /api/map/html    - 生成并返回 Folium 地图 HTML
GET /api/map/photos  - 获取指定城市的照片列表（热点点击后调用）
"""
import logging
import os

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.file import MediaFile

logger = logging.getLogger(__name__)
router = APIRouter()


# ── 共用：加载数据库文件 ─────────────────────────────────────

async def _load_files(
    db: AsyncSession,
    folder_path: str | None = None,
) -> list:
    """从数据库加载文件，可选按文件夹路径过滤"""
    if folder_path and folder_path.strip():
        norm = os.path.normpath(folder_path.strip())
        from sqlalchemy import or_
        result = await db.execute(
            select(MediaFile).where(
                or_(
                    MediaFile.original_path.like(f"{norm}%"),
                    MediaFile.original_path.like(f"{norm.replace(chr(92), '/')}%"),
                )
            ).order_by(MediaFile.datetime_original)
        )
    else:
        result = await db.execute(
            select(MediaFile).order_by(MediaFile.datetime_original)
        )
    return result.scalars().all()


# ── 接口实现 ─────────────────────────────────────────────────

@router.get("/map/html", response_class=HTMLResponse)
async def get_map_html(
    folder_path: str | None = Query(None, description="可选：只显示该文件夹的照片"),
    db: AsyncSession = Depends(get_db),
):
    """
    生成并返回 Folium 交互地图 HTML。

    前端通过 <iframe srcDoc="..."> 嵌入。
    地图中城市热点按钮点击时通过 window.parent.postMessage 通知父页面。
    """
    from app.services.map_service import generate_map_html

    files = await _load_files(db, folder_path)
    html = generate_map_html(files)
    return HTMLResponse(content=html)


@router.get("/map/photos")
async def get_map_photos(
    city: str | None = Query(None, description="城市名称（精确匹配）"),
    province: str | None = Query(None, description="省份名称（辅助筛选）"),
    limit: int = Query(60, ge=1, le=200, description="最大返回数量"),
    folder_path: str | None = Query(None, description="可选：限定文件夹范围"),
    db: AsyncSession = Depends(get_db),
):
    """
    获取指定城市的照片/视频列表。

    前端在地图热点点击后调用此接口，获取该热点的完整文件列表。
    """
    conditions = []

    if city:
        # 模糊匹配：支持 "哈尔滨 (Harbin)" 格式
        conditions.append(MediaFile.city.like(f"%{city}%"))
    elif province:
        conditions.append(MediaFile.province.like(f"%{province}%"))
    else:
        # 兜底：返回所有有 GPS 的文件
        conditions.append(MediaFile.has_gps == True)  # noqa

    # 文件夹过滤
    if folder_path and folder_path.strip():
        norm = os.path.normpath(folder_path.strip())
        from sqlalchemy import or_
        conditions.append(
            or_(
                MediaFile.original_path.like(f"{norm}%"),
                MediaFile.original_path.like(f"{norm.replace(chr(92), '/')}%"),
            )
        )

    from sqlalchemy import and_
    result = await db.execute(
        select(MediaFile)
        .where(and_(*conditions) if conditions else True)
        .order_by(MediaFile.datetime_original)
        .limit(limit)
    )
    files = result.scalars().all()

    return {
        "success": True,
        "data": {
            "city": city,
            "total": len(files),
            "files": [
                {
                    "id": f.id,
                    "file_name": f.file_name,
                    "file_type": f.file_type,
                    "original_path": f.original_path,
                    "current_path": f.current_path,
                    "datetime_original": f.datetime_original,
                    "latitude": f.latitude,
                    "longitude": f.longitude,
                    "city": f.city,
                    "province": f.province,
                    "country": f.country,
                }
                for f in files
            ],
        },
    }
