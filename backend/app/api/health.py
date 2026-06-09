"""健康检查接口"""
from fastapi import APIRouter
from app.core.config import settings

router = APIRouter()


@router.get("/health")
async def health_check():
    """健康检查，验证后端正常运行"""
    return {"status": "ok", "version": settings.app_version, "app": settings.app_name}
