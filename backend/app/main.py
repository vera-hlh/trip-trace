"""
TripTrace - FastAPI 后端入口
启动命令: uvicorn app.main:app --reload --port 17890
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import init_db
from app.api import health, scan, trips, archive, map_routes, media, video, config

app = FastAPI(
    title="TripTrace API",
    description="旅迹 · TripTrace 桌面工具后端 API",
    version="0.1.0",
)

# CORS 配置（允许 Electron 渲染进程访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境中限制为 electron://
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """应用启动时初始化数据库"""
    await init_db()


# 注册路由
app.include_router(health.router, tags=["系统"])
app.include_router(scan.router, prefix="/api", tags=["扫描"])
app.include_router(trips.router, prefix="/api", tags=["行程"])
app.include_router(archive.router, prefix="/api", tags=["归档"])
app.include_router(map_routes.router, prefix="/api", tags=["地图"])
app.include_router(media.router, prefix="/api", tags=["媒体"])
app.include_router(video.router, prefix="/api", tags=["视频"])
app.include_router(config.router, prefix="/api", tags=["配置"])
