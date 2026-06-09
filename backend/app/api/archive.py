"""归档操作接口 - TODO: Phase 2 实现"""
from fastapi import APIRouter
router = APIRouter()

@router.post("/archive/preview")
async def archive_preview(body: dict):
    return {"success": False, "error": "TODO: 待 Phase 2 实现"}

@router.post("/archive/execute")
async def archive_execute(body: dict):
    return {"success": False, "error": "TODO: 待 Phase 2 实现"}

@router.post("/archive/cleanup")
async def archive_cleanup(body: dict):
    return {"success": False, "error": "TODO: 待 Phase 2 实现"}
