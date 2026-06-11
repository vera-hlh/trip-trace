"""
行程管理接口

GET  /api/trips          - 获取行程列表（含子行程）
PUT  /api/trips/{id}     - 修改行程（重命名）
POST /api/trips/merge    - 合并两个子行程
POST /api/trips/split    - 拆分子行程
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.trip import Trip
from app.models.file import MediaFile

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================
# 请求/响应模型
# ============================================================

class TripUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    location_label: Optional[str] = None


class MergeRequest(BaseModel):
    trip_ids: list[int]
    new_name: Optional[str] = None


class SplitRequest(BaseModel):
    trip_id: int
    split_at: str  # ISO datetime 字符串


# ============================================================
# 接口实现
# ============================================================

@router.get("/trips")
async def get_trips(
    parent_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """获取行程列表（含子行程嵌套结构）"""
    try:
        if parent_id is not None:
            # 获取指定大行程的子行程
            result = await db.execute(
                select(Trip).where(Trip.parent_trip_id == parent_id)
                            .order_by(Trip.sequence_num)
            )
            subs = result.scalars().all()
            return {"success": True, "data": {"trips": [_trip_to_dict(t) for t in subs]}}

        # 获取所有大行程（parent_trip_id is NULL）
        result = await db.execute(
            select(Trip).where(Trip.parent_trip_id.is_(None))
                        .order_by(Trip.start_date)
        )
        big_trips = result.scalars().all()

        # 为每个大行程加载子行程
        trips_with_subs = []
        for big in big_trips:
            sub_result = await db.execute(
                select(Trip).where(Trip.parent_trip_id == big.id)
                            .order_by(Trip.sequence_num)
            )
            subs = sub_result.scalars().all()

            # 统计文件数
            file_count = await _count_files_in_trip(db, big.id, include_subs=True)

            trip_dict = _trip_to_dict(big)
            trip_dict["file_count"] = file_count
            trip_dict["sub_trips"] = []
            for sub in subs:
                sub_count = await _count_files_in_trip(db, sub.id)
                sub_dict = _trip_to_dict(sub)
                sub_dict["file_count"] = sub_count
                trip_dict["sub_trips"].append(sub_dict)

            trips_with_subs.append(trip_dict)

        return {"success": True, "data": {"trips": trips_with_subs}}

    except Exception as e:
        logger.error(f"获取行程列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/trips/{trip_id}")
async def update_trip(
    trip_id: int,
    body: TripUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """修改行程（重命名）"""
    result = await db.execute(select(Trip).where(Trip.id == trip_id))
    trip = result.scalar_one_or_none()
    if not trip:
        raise HTTPException(status_code=404, detail=f"行程不存在: {trip_id}")

    if body.display_name is not None:
        trip.display_name = body.display_name
    if body.location_label is not None:
        trip.location_label = body.location_label

    await db.commit()
    return {"success": True, "data": _trip_to_dict(trip)}


@router.post("/trips/merge")
async def merge_trips(
    body: MergeRequest,
    db: AsyncSession = Depends(get_db),
):
    """合并两个子行程（将第二个的文件移入第一个）"""
    if len(body.trip_ids) < 2:
        raise HTTPException(status_code=400, detail="至少需要两个行程 ID")

    # 获取第一个行程（作为合并目标）
    target_result = await db.execute(select(Trip).where(Trip.id == body.trip_ids[0]))
    target = target_result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail=f"行程不存在: {body.trip_ids[0]}")

    for trip_id in body.trip_ids[1:]:
        result = await db.execute(select(Trip).where(Trip.id == trip_id))
        trip = result.scalar_one_or_none()
        if not trip:
            continue

        # 将该行程的文件移到目标行程
        files_result = await db.execute(
            select(MediaFile).where(MediaFile.trip_id == trip_id)
        )
        for f in files_result.scalars():
            f.trip_id = target.id

        await db.delete(trip)

    if body.new_name:
        target.display_name = body.new_name
    target.user_merged = True
    await db.commit()

    return {"success": True, "message": f"已合并 {len(body.trip_ids)} 个行程"}


# ============================================================
# 辅助函数
# ============================================================

def _trip_to_dict(trip: Trip) -> dict:
    return {
        "id": trip.id,
        "trip_name": trip.trip_name,
        "display_name": trip.display_name or trip.trip_name,
        "start_date": trip.start_date,
        "end_date": trip.end_date,
        "parent_trip_id": trip.parent_trip_id,
        "sequence_num": trip.sequence_num,
        "location_label": trip.location_label,
        "user_merged": trip.user_merged,
    }


async def _count_files_in_trip(
    db: AsyncSession,
    trip_id: int,
    include_subs: bool = False,
) -> int:
    """统计某个行程的文件数（可选是否包含子行程）"""
    from sqlalchemy import func

    if not include_subs:
        result = await db.execute(
            select(func.count(MediaFile.id)).where(MediaFile.trip_id == trip_id)
        )
        return result.scalar() or 0

    # 包含子行程
    sub_result = await db.execute(
        select(Trip.id).where(Trip.parent_trip_id == trip_id)
    )
    sub_ids = [row[0] for row in sub_result.all()]

    all_ids = [trip_id] + sub_ids
    result = await db.execute(
        select(func.count(MediaFile.id)).where(MediaFile.trip_id.in_(all_ids))
    )
    return result.scalar() or 0
