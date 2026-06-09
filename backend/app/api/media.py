"""媒体文件接口 - TODO: Phase 2 实现"""
from fastapi import APIRouter
router = APIRouter()

@router.get("/media/thumbnail")
async def get_thumbnail(path: str, width: int = 400, quality: int = 75):
    return {"success": False, "error": "TODO: 待 Phase 2 实现"}
