"""视频导出接口 - TODO: Phase 4 实现"""
from fastapi import APIRouter
router = APIRouter()

@router.post("/video/export")
async def export_video(body: dict):
    return {"success": False, "error": "TODO: 待 Phase 4 实现"}
