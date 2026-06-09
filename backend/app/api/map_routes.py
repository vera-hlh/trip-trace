"""地图生成接口 - TODO: Phase 3 实现"""
from fastapi import APIRouter
router = APIRouter()

@router.get("/map/html/{trip_id}")
async def get_map_html(trip_id: int):
    return {"success": False, "error": "TODO: 待 Phase 3 实现"}
