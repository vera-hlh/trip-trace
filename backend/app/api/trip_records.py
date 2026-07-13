"""
「我的旅迹」记录接口

GET /api/trips/records         - 分页获取已归档大行程记录（支持排序）
GET /api/trips/records/recent  - 获取最近N条记录（首页预览用）
"""
import logging
import math

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.trip_record import TripRecord

logger = logging.getLogger(__name__)
router = APIRouter()


# ── 排序选项映射 ─────────────────────────────────────────────

_SORT_MAP = {
    "trip_date_desc":    (TripRecord.start_date, True),   # 大行程日期降序（默认）
    "trip_date_asc":     (TripRecord.start_date, False),  # 大行程日期升序
    "created_at_desc":   (TripRecord.created_at, True),   # 生成时间降序
    "created_at_asc":    (TripRecord.created_at, False),  # 生成时间升序
}


def _record_to_dict(r: TripRecord) -> dict:
    return {
        "id": r.id,
        "big_trip_name": r.big_trip_name,
        "start_date": r.start_date,
        "end_date": r.end_date,
        "sub_trip_count": r.sub_trip_count,
        "total_files": r.total_files,
        "output_folder": r.output_folder,
        "big_trip_folder": r.big_trip_folder,
        "created_at": r.created_at,
        "poster_path": r.poster_path,
    }


@router.get("/trips/records")
async def get_trip_records(
    page: int = Query(1, ge=1, description="页码（从1开始）"),
    page_size: int = Query(6, ge=1, le=50, description="每页条数"),
    sort: str = Query("trip_date_desc", description="排序方式"),
    db: AsyncSession = Depends(get_db),
):
    """
    分页获取「我的旅迹」记录列表。

    sort 可选值：
      trip_date_desc（默认，大行程日期降序）
      trip_date_asc（大行程日期升序）
      created_at_desc（生成时间降序）
      created_at_asc（生成时间升序）
    """
    sort_col, is_desc = _SORT_MAP.get(sort, _SORT_MAP["trip_date_desc"])
    order_clause = sort_col.desc() if is_desc else sort_col.asc()

    # 总数
    total_result = await db.execute(select(func.count(TripRecord.id)))
    total = total_result.scalar() or 0
    total_pages = max(1, math.ceil(total / page_size))
    page = min(page, total_pages)  # 防止页码越界

    result = await db.execute(
        select(TripRecord)
        .order_by(order_clause)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    records = result.scalars().all()

    return {
        "success": True,
        "data": {
            "records": [_record_to_dict(r) for r in records],
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        },
    }


@router.get("/trips/records/recent")
async def get_recent_trip_records(
    limit: int = Query(5, ge=1, le=20, description="返回条数"),
    db: AsyncSession = Depends(get_db),
):
    """获取最近的N条「我的旅迹」记录（首页预览版块用，按生成时间倒序）"""
    result = await db.execute(
        select(TripRecord)
        .order_by(TripRecord.created_at.desc())
        .limit(limit)
    )
    records = result.scalars().all()

    return {
        "success": True,
        "data": {
            "records": [_record_to_dict(r) for r in records],
            "total": len(records),
        },
    }


@router.get("/trips/records/{record_id}")
async def get_trip_record_detail(
    record_id: int,
    db: AsyncSession = Depends(get_db),
):
    """获取单条「我的旅迹」记录详情（含子行程JSON，供海报预览区使用）"""
    import json as _json

    result = await db.execute(
        select(TripRecord).where(TripRecord.id == record_id)
    )
    record = result.scalar_one_or_none()

    if not record:
        return {"success": False, "error": "记录不存在"}

    sub_trips = []
    if record.sub_trips_json:
        try:
            sub_trips = _json.loads(record.sub_trips_json)
        except Exception:
            sub_trips = []

    data = _record_to_dict(record)
    data["sub_trips"] = sub_trips

    return {"success": True, "data": data}
