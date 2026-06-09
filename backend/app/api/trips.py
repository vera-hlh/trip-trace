"""行程管理接口 - TODO: Phase 2 实现"""
from fastapi import APIRouter
router = APIRouter()

@router.get("/trips")
async def get_trips():
    return {"success": True, "data": {"trips": []}}
