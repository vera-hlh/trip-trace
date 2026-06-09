"""扫描文件夹接口 - TODO: Phase 2 实现"""
from fastapi import APIRouter
router = APIRouter()

@router.post("/scan")
async def scan_folder(body: dict):
    """扫描文件夹，提取媒体文件元数据（待实现）"""
    return {"success": False, "error": "TODO: 待 Phase 2 实现"}
