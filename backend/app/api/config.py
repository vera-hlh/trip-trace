"""配置接口"""
from fastapi import APIRouter
from app.core.config import settings
router = APIRouter()

@router.get("/config")
async def get_config():
    return {
        "success": True,
        "data": {
            "gaode_api_key": settings.gaode_api_key,
            "big_trip_threshold_days": settings.big_trip_threshold_days,
            "small_trip_threshold_hours": settings.small_trip_threshold_hours,
            "default_granularity": settings.default_granularity,
        }
    }
